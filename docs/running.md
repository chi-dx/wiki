# 运行初版

当前版本可在没有API密钥的情况下运行。内置8篇虚构Wiki与3篇模拟外部资料，覆盖性能测试、Profiling、SVE、Velox、芯片和迭代交付。页面和原文明确标注虚构资料。

当前采用Karpathy的llm-wiki思路实现持久化知识层：先生成单资料页和主题页，再用轻量中文二元词与英文术语匹配检索知识页，映射到原文证据。支持哈希更新、Markdown导出和事务发布。默认编译与回答均为摘录模式，只有显式配置模型后才生成摘要、跨资料综合与融合答案。见[实现说明](llm-wiki.md)。

## Windows启动

在项目根目录执行。需要uv；本次开发环境已下载到忽略Git的`.tools/uv.exe`，也可使用自己安装的`uv`替代。

```powershell
.tools/uv.exe sync --locked
Copy-Item .env.example .env
.tools/uv.exe run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

已有`.env`时不要覆盖。打开 <http://127.0.0.1:8000>。演示模式首次启动自动导入示例，无需额外任务即可体验。

若要测试后续增量同步，另开终端运行：

```powershell
.tools/uv.exe run python -m app.sync
```

编辑`fixtures/wiki.json`后，后台任务会按周期重新扫描；也可执行`.tools/uv.exe run python -m app.sync --once`立即同步。只启动一个周期同步实例。

## Linux Docker部署

安装Docker和Compose后，在仓库根目录复制配置并启动：

```sh
cp .env.example .env
docker compose up -d --build
docker compose logs -f web sync
```

访问服务器8000端口。Web与同步进程共用命名数据卷；`docker compose down`保留数据，不要使用`down -v`删除数据卷，除非明确需要清空。

如不能使用Docker，可安装uv后执行`uv sync --locked --no-dev`，然后分别运行`uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`和`uv run python -m app.sync`，用服务器进程管理器保活。

Docker配置已提供，但当前Windows环境未进行Linux容器或ARM64实机验证。依赖锁文件固定依赖解析，目标架构仍需实际构建测试。

## 接入模型

在`.env`设置以下参数，重启Web服务：

```dotenv
MODEL_MODE=openai
MODEL_URL=https://your-gateway.example/v1/chat/completions
MODEL_API_KEY=your-key
MODEL_NAME=your-model
```

当前适配器只支持OpenAI兼容的Chat Completions请求协议，不代表所有模型厂商都兼容。模型返回空答案、缺引用或引用不存在时，降级为资料列表，不虚构生成成功。需使用其他协议时修改`app/providers.py`的生成适配器。

若同时启用入库阶段的模型知识编译，再设置`COMPILE_MODE=llm`，并执行`uv run python -m app.sync --once`。编译与问答分别控制：`COMPILE_MODE`控制持久化知识页，`MODEL_MODE`控制在线回答。模型编译按变更资料调用API，可能产生费用；未配置模型时保持`COMPILE_MODE=extractive`。

门户右上角“编译知识目录”对应`/wiki`，可查看资料页、主题页及原文链接。Markdown目录为`data/vault/generations/<版本ID>/`，当前版本ID可从`GET /api/wiki`的`compilation.generation`读取。

## 接入Wiki和外部资料

目前HTTP接口是本项目约定的适配契约，尚未对接实际Wiki或hisi接口。真实系统字段不同时修改适配器，不能直接假定兼容。

`WIKI_MODE=http`时配置`WIKI_URL`及可选的`WIKI_API_KEY`。GET接口需返回完整权威快照：

```json
{
  "complete": true,
  "documents": [{
    "id": "doc-1",
    "title": "文档标题",
    "category": "性能方法",
    "tags": ["perf"],
    "body": "## 章节\n正文",
    "version": "1",
    "updated_at": "2026-09-16",
    "url": "https://your-wiki.example/doc-1",
    "fictional": false
  }]
}
```

初版拉取全量快照，通过内容和元数据哈希判断哪些文档需要重新索引。版本参与哈希，但尚未实现源端版本列表和正文分离请求。`complete`不为`true`、重复ID、任何文档验证失败或HTTP失败都会拒绝发布并保留旧索引。完整空快照表示明确清空；上游适配器不得将失败转换成空列表。

`EXTERNAL_MODE=http`时配置`EXTERNAL_URL`及可选的`EXTERNAL_API_KEY`，后端发送`POST {"question":"问题","limit":4}`，预期返回：

```json
{
  "results": [{
    "evidence_id": "other:doc-1:section-2",
    "source_name": "其他团队资料库",
    "title": "原文标题",
    "url": "https://other-wiki.example/doc-1",
    "text": "可追溯的原文片段",
    "updated_at": "2026-09-16",
    "fictional": false
  }]
}
```

此契约要求原文片段及出处；若真实接口仅返回生成答案，需单独适配，不能伪装成原文。两类HTTP适配器使用Bearer密钥，无密钥时不发送Authorization。

切换到真实资料后建议使用新的`DATA_DIR`，完成首次同步再对外提供，避免把旧演示快照误当作真实资料。`EXTERNAL_MODE=off`可完全关闭外部检索。

## 数据与运维

- 数据默认保存在`data/wiki.sqlite3`：文档快照、章节索引、编译知识页、同步状态、问答证据快照及反馈；`data/vault/generations/`保存不可变Markdown版本目录。
- 当前事务内同时更新文档和索引，失败时旧版本保持可读；没有额外向量服务。
- 问答有并发限制、检索超时和生成降级。请求日志不输出密钥，资料文本不会插入可执行HTML。
- `/health/live`检查进程；`/health/ready`检查首次同步及数据库索引可读性。
- 停止Web与同步进程后备份整个数据目录；恢复时也先停服务。问答记录暂未实现自动清理，实际使用前需确定保留周期。
- 权限、原文维护、图片OCR、附件解析和正式效果评测未实现。知识编译已按Karpathy思路实现，但尚未用真实模型验证内容质量。

## 开发检查

```powershell
.tools/uv.exe run pytest -q
```

测试覆盖同步增量、删除、失败保留、两路检索、引用、降级、反馈持久化和页面内容转义。它们用于验证代码行为，不是知识问答质量验收题集。
