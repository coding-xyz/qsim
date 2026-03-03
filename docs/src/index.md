# qsim 文档

`docs/` 是项目统一的文档根目录，包含两类内容：

- [Wiki](WIKI.md)：面向实现、设计和使用方式的说明
- [API Reference](api/index.md)：基于源码 `docstring` 自动生成的接口参考

## 目录约定

- `docs/src/`：文档源文件、Wiki 页面、API 生成脚本
- `docs/site/`：`mkdocs build --clean` 生成的静态站点，不直接手改

## 快速开始

安装文档依赖：

```bash
pip install -e .[docs]
```

本地预览：

```bash
mkdocs serve
```

构建静态站点：

```bash
mkdocs build --clean
```

## 维护规则

- 所有源码、文档、issue 和配置文件统一使用 UTF-8 编码。
- 编辑文档时只修改 `docs/src/` 或其他文档源文件，不直接修改 `docs/site/`。
- API 页面以源码 `docstring` 为准，代码改动后应同步更新相关 `docstring`。
- 代码改动如果影响行为、接口、配置或使用方式，应同步更新 `docs/` 中对应内容。

## 提交前检查

安装开发用检查工具：

```bash
pip install -e .[dev]
pre-commit install
```

手动执行全部检查：

```bash
pre-commit run --all-files
```

当前自动检查包括：

- 常见文本文件必须为 UTF-8
- 禁止直接提交 `docs/site/` 下的生成产物修改
- YAML 基本校验
- 合并冲突标记检查
- 行尾、末尾换行和空白规范化
