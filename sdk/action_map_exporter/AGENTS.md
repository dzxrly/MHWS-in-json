# 武器动作映射提取与维护

> ActionMap 是武器动作与碰撞 requestSet 的静态映射 JSON，由表格构建器消费；精确身份为 scope、RCOL 路径、requestSet ID、key hash 和源序号的五元组。

本目录是离线 Python SDK。输入为同一游戏导出的内存 dump EXE、IL2CPP JSON，以及 `MHWS-in-json/natives` 中转换后的 MOTBANK、MOTLIST、PFB、RCOL 和 USER JSON。入口为 `python -m sdk.action_map_exporter extract`，默认输出 `MHWS-in-json/ActionMap.json`。EXE 与 IL2CPP 用 `-e/-i` 或 `MHWS_EXE/MHWS_IL2CPP` 指定，不猜测安装路径。

## 维护边界

- 不运行游戏或 EXE，不注入或 Hook；EXE 只作为字节数据读取。
- SDK 与 `src`、`web` 只通过 JSON 交接，不能互相导入。不要依赖另一仓库的 Python 模块、PAK、Release list、原始 PFB/MOTBANK、REE-Lib 或 .NET。
- 调试输出与一次性脚本放在项目根目录 `.tmp`，不提交 EXE、IL2CPP、反汇编缓存。
- `motlist-to-json` 负责独立格式转换，本目录独立检查所需资源及其引用闭包。无关 PFB 失败不阻断 ActionMap；必需资源缺失、引用歧义与损坏格式必须报错，不能使用旧文件静默兜底。
- Schema 在 `data/action-map-v2.schema.json`，生成端测试在 `tests/sdk/action_map`；`src/shared/action_values/action_map.py` 独立检查消费契约。两端字段、枚举和精确身份规则变化时同步维护。
- 只有直接游戏代码或资源证据支持的关系才能标记为 `proven`；推导关系保留 `derived` 或 `structural`。继承、运行时规则、未解析动作和条件均须保留，不能为提高覆盖率而升级证据等级。
- 保持确定性排序与原子写出。生成失败时保留原输出；临时生成使用 `-o .tmp/action-map/ActionMap.json`。
- 同次生成只流式扫描一次 IL2CPP，保留精简的方法、继承、动作字段及全局函数地址索引，以及原生规则必需的少量类型记录。先用同源严格索引完成原生规则校验，再从内存选择动作方法；禁止为规则校验与动作扫描分别完整读取 metadata，不把完整 dump 载入内存或增加跨运行磁盘缓存。

## 游戏更新

1. 转换新版资源并复制进项目，使用同一更新后的 EXE 和 IL2CPP 重建 ActionMap。
2. 碰撞规则中的版本常量必须由 `shared/native_validation.py` 和 `data/native_rules.v1.json` 核对。方法按类型、去后缀名称和签名定位；完整指令、被调方身份、引用表、布局或枚举变化时先复核原生代码。不能只刷新证明以绕过检查，也不能因所有 ID 仍存在就认定规则有效。
3. 对比关系、条件、证据等级、未解析项和统计，再用实际 RCOL 按完整五元组绑定。地址移动与业务规则改变分开判断。
4. 运行相关 SDK 与消费者测试，实际导出 `WeaponActionValues.xlsx`；其他技能、怪物 JSON 由各自 SDK 更新。
5. 命令或参数变化时同步更新 `sdk/README.md`、`sdk/docs/README.zh-Hans.md`、`sdk/docs/README.zh-Hant.md` 及三份主 README 的相关入口。
