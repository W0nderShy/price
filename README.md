# 自动化比价脚本（Meruki -> 闲鱼）

这个仓库提供了一个 Python 自动化脚本，流程如下：

1. 自动打开 `https://meruki.cn/`
2. 在站内搜索（默认关键词：`spark 1/43`）
3. 把搜索结果名称整理成：`spark` + `1/43` + `对应赛车名字`
4. 将整理后的名称输入 `https://www.goofish.com/`（闲鱼）搜索，并抓取价格做简单比价

> 说明：网站前端结构可能变化，脚本已把关键选择器做成可配置参数。

## 1) 环境配置

### 系统要求
- Python 3.10+
- 已安装本地 Chrome（不是 Chromium）
- Chrome 里已登录你自己的账号（复用个人资料）

### 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip playwright
python -m playwright install chrome
```

## 2) 使用本地 Chrome 个人资料（免重复登录）

脚本使用 `playwright.launch_persistent_context`，直接复用本机 Chrome 用户数据目录。

常见目录：

- macOS: `~/Library/Application Support/Google/Chrome`
- Linux: `~/.config/google-chrome`
- Windows: `%LOCALAPPDATA%\Google\Chrome\User Data`

你需要传入：
- `--chrome-user-data-dir`：用户数据目录（User Data）
- `--chrome-profile`：具体 profile 名称（常见是 `Default` / `Profile 1`）

## 3) 运行示例

```bash
python scripts/auto_price_compare.py \
  --chrome-user-data-dir "$HOME/.config/google-chrome" \
  --chrome-profile "Default" \
  --query "spark 1/43" \
  --output output/price_compare.csv
```

运行后会输出 CSV：
- `source_name`：Meruki 原名称
- `normalized_name`：整理后的名称
- `min_price`：闲鱼抓到的最低价
- `avg_price`：闲鱼抓到的平均价
- `prices`：抓到的价格列表

## 4) 可调参数（应对页面变动）

如果页面结构变化，可手动调整：

- `--meruki-search-selector`
- `--meruki-result-selector`
- `--goofish-search-selector`
- `--goofish-price-selector`
- `--wait-seconds`

例如：

```bash
python scripts/auto_price_compare.py \
  --chrome-user-data-dir "$HOME/.config/google-chrome" \
  --meruki-search-selector "input[placeholder*='搜索']" \
  --meruki-result-selector ".goods-title" \
  --goofish-search-selector "input[placeholder*='搜索']" \
  --goofish-price-selector ".price"
```

## 5) 注意事项

- 第一次跑建议 `--headless` 不要开，先观察页面是否正确操作。
- 闲鱼可能有风控/验证码，建议手动登录并保持会话后再跑。
- 脚本仅做信息抓取与比价演示，请遵守目标站点服务条款。
