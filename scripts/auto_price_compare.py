#!/usr/bin/env python3
"""Automate model car price comparison between Meruki and Goofish using local Chrome profile.

Workflow:
1. Open Meruki and perform search with keyword (default: "spark 1/43").
2. Normalize each Meruki result name to: "spark" + "1/43" + <car model name>.
3. Search normalized names on Goofish and collect listed prices for comparison.

Notes:
- This script intentionally uses local Chrome + existing user profile so login/session can be reused.
- Website DOM may change; selectors are configurable via arguments.
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from playwright.sync_api import Page, TimeoutError, sync_playwright


@dataclass
class CompareResult:
    source_name: str
    normalized_name: str
    prices: list[float]

    @property
    def min_price(self) -> float | None:
        return min(self.prices) if self.prices else None

    @property
    def avg_price(self) -> float | None:
        return statistics.mean(self.prices) if self.prices else None


PRICE_RE = re.compile(r"(?:¥|￥)?\s*([0-9]+(?:\.[0-9]+)?)")


def parse_price(text: str) -> float | None:
    m = PRICE_RE.search(text.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def normalize_name(raw_name: str, prefix_brand: str = "spark", scale: str = "1/43") -> str:
    """Normalize to format: spark + 1/43 + <car name>.

    We strip repeated brand/scale markers from the raw string, then prepend fixed format.
    """
    text = re.sub(r"\s+", " ", raw_name).strip()
    text = re.sub(r"(?i)\bspark\b", "", text)
    text = text.replace("1:43", "").replace("1/43", "")
    text = re.sub(r"\s+", " ", text).strip(" -_")
    return f"{prefix_brand} {scale} {text}".strip()


def safe_fill_and_enter(page: Page, selector: str, text: str) -> None:
    page.locator(selector).first.click(timeout=5000)
    page.locator(selector).first.fill(text)
    page.keyboard.press("Enter")


def get_meruki_result_names(
    page: Page,
    query: str,
    search_input_selector: str,
    result_name_selector: str,
    wait_seconds: float,
) -> list[str]:
    page.goto("https://meruki.cn/", wait_until="domcontentloaded")
    safe_fill_and_enter(page, search_input_selector, query)
    time.sleep(wait_seconds)

    elements = page.locator(result_name_selector)
    count = elements.count()
    names: list[str] = []
    for i in range(count):
        text = elements.nth(i).inner_text().strip()
        if text:
            names.append(text)

    # Deduplicate preserving order.
    return list(dict.fromkeys(names))


def collect_goofish_prices(
    page: Page,
    search_name: str,
    goofish_url: str,
    search_input_selector: str,
    result_price_selector: str,
    wait_seconds: float,
    max_items: int,
) -> list[float]:
    page.goto(goofish_url, wait_until="domcontentloaded")
    safe_fill_and_enter(page, search_input_selector, search_name)
    time.sleep(wait_seconds)

    prices: list[float] = []
    rows = page.locator(result_price_selector)
    row_count = min(rows.count(), max_items)
    for i in range(row_count):
        raw = rows.nth(i).inner_text()
        parsed = parse_price(raw)
        if parsed is not None:
            prices.append(parsed)
    return prices


def write_csv(results: Iterable[CompareResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source_name", "normalized_name", "min_price", "avg_price", "prices"])
        for row in results:
            writer.writerow(
                [
                    row.source_name,
                    row.normalized_name,
                    f"{row.min_price:.2f}" if row.min_price is not None else "",
                    f"{row.avg_price:.2f}" if row.avg_price is not None else "",
                    "|".join(f"{p:.2f}" for p in row.prices),
                ]
            )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Automate Meruki -> Goofish price comparison")
    p.add_argument("--query", default="spark 1/43", help="Meruki search keyword")
    p.add_argument("--chrome-user-data-dir", required=True, help="Chrome user data dir")
    p.add_argument("--chrome-profile", default="Default", help="Chrome profile directory name")
    p.add_argument("--headless", action="store_true", help="Run headless (not recommended for login-protected pages)")
    p.add_argument("--meruki-search-selector", default="input[type='search'], input[placeholder*='搜索']")
    p.add_argument("--meruki-result-selector", default=".product-title, .goods-title, [class*='title']")
    p.add_argument("--goofish-url", default="https://www.goofish.com/")
    p.add_argument("--goofish-search-selector", default="input[type='search'], input[placeholder*='搜索']")
    p.add_argument("--goofish-price-selector", default="[class*='price'], .price")
    p.add_argument("--wait-seconds", type=float, default=4.0, help="Static wait after searching")
    p.add_argument("--max-source-items", type=int, default=10)
    p.add_argument("--max-price-items", type=int, default=20)
    p.add_argument("--output", default="output/price_compare.csv")
    return p


def main() -> None:
    args = build_parser().parse_args()
    output_path = Path(args.output)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=args.chrome_user_data_dir,
            channel="chrome",
            headless=args.headless,
            args=[f"--profile-directory={args.chrome_profile}"],
            viewport={"width": 1440, "height": 900},
        )

        page = context.new_page()
        try:
            source_names = get_meruki_result_names(
                page,
                query=args.query,
                search_input_selector=args.meruki_search_selector,
                result_name_selector=args.meruki_result_selector,
                wait_seconds=args.wait_seconds,
            )
        except TimeoutError as e:
            context.close()
            raise RuntimeError("Meruki page interaction timeout. Please adjust selectors/wait time.") from e

        if not source_names:
            context.close()
            raise RuntimeError("No Meruki result names captured. Please check selectors.")

        results: list[CompareResult] = []
        for source in source_names[: args.max_source_items]:
            normalized = normalize_name(source)
            try:
                prices = collect_goofish_prices(
                    page,
                    search_name=normalized,
                    goofish_url=args.goofish_url,
                    search_input_selector=args.goofish_search_selector,
                    result_price_selector=args.goofish_price_selector,
                    wait_seconds=args.wait_seconds,
                    max_items=args.max_price_items,
                )
            except TimeoutError:
                prices = []
            results.append(CompareResult(source, normalized, prices))

        write_csv(results, output_path)
        context.close()

    print(f"Done. Wrote comparison result to: {output_path}")


if __name__ == "__main__":
    main()
