# qsim 文档

本目录包含两部分：

- [Wiki](WIKI.md)：实现说明、限制说明、建议阅读顺序。
- [API Reference](api/index.md)：由源码 docstring 自动生成。

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
mkdocs build
```

## Docs Directory vs Site Directory

- `docs/`: source markdown and doc-generation scripts tracked as editable documentation sources.
- `site/`: generated static website output from `mkdocs build`.

They are not duplicated functionality:
- edit content in `docs/`
- preview/build output in `site/`

Recommended workflow:

```bash
mkdocs serve   # local preview
mkdocs build   # regenerate site/
```
