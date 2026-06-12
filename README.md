# 决策引擎与模型意图识别自动化测试框架

## 项目简介

本项目是一个基于 pytest 的自动化测试框架，覆盖两大核心测试领域：

1. **决策引擎系统测试**：测试流程引擎、米霍克决策引擎和特征平台三大模块的功能
2. **信贷模型意图识别测试**：基于 LLM-as-Judge 的模型意图识别自动化测试框架，支持单轮/多轮对话的质量评估

## 项目结构

```
making_decison_test/
├── test_cases/                      # 测试用例目录
│   ├── test_process_engine.py              # 流程引擎测试用例
│   ├── test_mihawk_engine.py              # 米霍克引擎测试用例
│   ├── test_feature_platform.py           # 特征平台测试用例
│   └── test_model_intent_recognition.py   # 模型意图识别测试用例（单轮/多轮）
│
├── script_code/                      # 执行脚本目录
│   ├── process_engine_exec.py             # 流程引擎执行脚本
│   ├── mihawk_engine_exec.py              # 米霍克引擎执行脚本
│   ├── feature_platform_exec.py          # 特征平台执行脚本
│   ├── postloan_touch_platform_exec.py   # 贷后触达平台执行脚本
│   └── offer_service_exec.py             # Offer服务执行脚本
│
├── common/                           # 公共模块目录
│   ├── baseRpc.py                       # RPC基础类
│   ├── rpcAction.py                     # RPC操作封装
│   ├── dbAction.py                      # 数据库操作封装
│   ├── ckAction.py                      # ClickHouse操作封装
│   ├── httpAction.py                    # HTTP请求操作封装
│   ├── modelHttpAction.py               # 模型HTTP请求操作封装（意图识别模型调用）
│   ├── riskMock.py                      # 风控Mock
│   └── postLoanAction.py                # 贷后操作封装
│
├── utils/                            # 工具模块目录
│   ├── handle_yaml.py                   # YAML文件处理工具
│   ├── handle_log.py                    # 日志处理工具（基于loguru）
│   ├── handle_path.py                   # 路径处理工具
│   ├── handle_cases.py                  # 测试用例处理工具
│   ├── handle_model_cases.py            # 模型测试用例处理工具（意图识别用例组装）
│   ├── handle_plot.py                   # 图表绘制工具（雷达图等）
│   ├── handle_allure_report.py          # Allure报告统计与企微通知工具
│   ├── handle_wechat_notify.py          # 企业微信通知工具
│   ├── batch_assert_collector.py        # 批量断言数据收集器（session finish阶段聚合）
│   ├── rate_limiter.py                  # API限流工具
│   └── handle_instanceid.py            # 实例ID处理工具
│
├── assert_code/                      # 断言模块目录
│   ├── assertAction.py                  # 通用断言操作类
│   ├── assert_decorators.py            # 断言装饰器
│   ├── model_intent_assert.py          # 模型意图识别断言（单轮/多轮）
│   ├── external_model_judge.py         # 外部模型评判（细粒度检查清单评分器）
│   ├── multi_turn_llm_judge.py        # 多轮对话LLM质量评估器（G1/G2/Q1-Q5）
│   ├── multi_turn_enhanced_evaluator.py # 多轮对话增强评估器（LLM Judge + 状态转移验证 + 一致性检查）
│   ├── session_state_validator.py      # 会话状态转移合规性验证器
│   ├── batch_assert_strategies.py      # 批量断言策略（单轮/多轮）
│   ├── batch_model_assert.py           # 批量模型断言（批量评估 + 报告生成）
│   ├── knowledge_base.py              # 意图知识库
│   └── intent_confusion_matrix.py     # 意图混淆矩阵分析工具
│
├── config/                           # 配置文件目录
│   ├── env_group_config.yaml           # 测试环境配置文件
│   ├── process_para_format.yaml        # 流程引擎参数格式配置
│   ├── package_para_format.yaml        # 乐包引擎参数格式配置
│   ├── feature_para_format.yaml        # 特征平台参数格式配置
│   ├── execute_res_schema.yaml         # 执行结果Schema配置
│   ├── execute_res_db_assert.yaml      # 执行结果数据库断言配置
│   ├── model_knowledge_base.yaml       # 模型意图知识库配置
│   ├── model_intent_reply_rules.yaml # 模型意图回复规则配置
│   ├── model_intent_checklist.yaml   # 模型意图检查清单配置
│   └── model_multi_turn_knowledge_base.yaml # 多轮对话评估知识库
│
├── docs/                             # 文档目录
│   ├── standard_QA_intent.md          # 标准QA意图文档
│   ├── session_state_transition.md    # 会话状态转移矩阵文档
│   └── intent_taxonomy.md             # 意图分类体系文档
│
├── model_skills/                     # 模型测试技能文档
│   ├── gen_single_round_cases.md      # 单轮意图测试用例生成指南
│   └── gen_multi_rounds_cases.md     # 多轮对话测试用例生成指南
│
├── case_data/                        # 测试用例数据目录（Excel格式）
│   ├── pro_process_test_cases.xlsx        # 生产环境流程测试用例
│   ├── pro_package_test_cases.xlsx        # 生产环境乐包测试用例
│   ├── pro_feature_test_cases.xlsx        # 生产环境特征测试用例
│   ├── *_(yn/mxg)_(stable/pro)_*_test_cases.xlsx  # 各环境测试用例
│   └── ...
│
├── report/                           # 测试报告目录
│   ├── tmp/                            # Allure临时数据
│   ├── report/                         # Allure测试报告
│   └── model_intent_recognition/       # 模型意图识别测试报告（CSV/HTML）
│
├── exec_pytest.py                    # pytest执行入口文件
├── debug_model_by_pytest.py          # 模型调试执行入口（支持单case调试）
├── pytest.ini                        # pytest配置文件
├── requirements.txt                  # 项目依赖文件
├── README.md                         # 项目说明文档
└── 使用指南.md                       # 详细使用指南
```

## 测试模块说明

### 1. 决策引擎测试

#### 流程引擎测试 (test_process_engine.py)
测试流程引擎的在线实时决策和离线批跑决策功能
- **在线实时决策**: 执行在线决策并验证结果
- **离线批跑决策**: 执行批量决策并验证结果

#### 米霍克引擎测试 (test_mihawk_engine.py)
测试米霍克决策引擎的多种决策模式
- **流程决策**: 在线/批跑/仿真模式的流程决策
- **节点决策**: 在线/批跑模式的节点决策
- **乐包决策**: 在线/批跑模式的乐包决策

#### 特征平台测试 (test_feature_platform.py)
测试特征平台的字段计算功能
- **授信代理层**: 字段批量拉取
- **交易代理层**: 字段获取
- **仿真代理层**: 字段获取
- **业务代理层**: 字段获取
- **离线代理层**: 字段获取

### 2. 模型意图识别测试 (test_model_intent_recognition.py)

基于 LLM-as-Judge 的信贷模型意图识别自动化测试框架，支持单轮和多轮对话测试。

#### 单轮测试模式
- **意图分类断言**: 验证模型是否正确识别用户意图
- **语义相似度评估**: 对比模型回复与标准答案的语义相似度
- **ASSET卡片断言**: 验证模型返回的业务参数卡片是否符合预期
- **转人工断言**: 验证模型在适当场景下是否正确转人工
- **细粒度检查清单**: 基于 YAML 配置的检查清单（事实/逻辑/安全维度）

#### 多轮测试模式
- **上下文记忆评估**: 验证模型是否记住前文关键信息
- **意图转移应对**: 验证用户切换话题时模型是否正确应对
- **上下文污染检测**: 验证切换话题后旧话题信息是否混入新回复
- **信息一致性检查**: 验证多轮中提供的数字、金额等信息是否前后一致
- **会话状态转移验证**: 基于状态转移矩阵验证会话状态流转是否合规

#### 批量断言模式
- **批量单轮评估**: 一次性评估多条单轮用例
- **批量多轮评估**: 一次性评估多条多轮对话用例
- **自动生成报告**: CSV详细结果 + HTML可视化报告（含雷达图）
- **企微通知**: 执行完成后自动发送测试结果到企业微信

## 核心功能类

### 决策引擎断言类

#### 1. 通用断言 (assert_code/assertAction.py)
- `value_assert(data, assert_rules, desc)` - 值断言，支持精确匹配和JsonPath表达式

### 模型意图识别评估类

#### 2. 外部模型评判器 (assert_code/external_model_judge.py)
```python
from assert_code.external_model_judge import ExternalModelJudge

judge = ExternalModelJudge(strategy="balanced")
result = judge.evaluate(actual_answer, expected_answer)
# result.verdict: 通过/条件通过/失败
# result.score: 0.0 ~ 1.0
# result.items: 各检查项详情
```

#### 3. 多轮对话LLM评估器 (assert_code/multi_turn_llm_judge.py)
```python
from assert_code.multi_turn_llm_judge import MultiTurnLLMJudge

judge = MultiTurnLLMJudge(model_name='kimi-k2.6')
dialogue = [
    {'turn': 1, 'user_question': '我想提额', 'model_response': '...'},
    {'turn': 2, 'user_question': '需要什么条件？', 'model_response': '...'},
]
result = judge.evaluate(dialogue, case_id='MD_0001')
# result.overall_score: 综合评分
# result.gate_passed: 底线是否通过
# result.dimension_scores: 各维度得分
```

#### 4. 会话状态验证器 (assert_code/session_state_validator.py)
```python
from assert_code.session_state_validator import SessionStateValidator

validator = SessionStateValidator(mode='strict')
trajectory = [
    {'turn': 1, 'current_state': 'INIT', 'detected_intent': '提额业务咨询'},
    {'turn': 2, 'current_state': 'TL_YWZX', 'detected_intent': '提额准入条件咨询'},
]
result = validator.validate_multi_turn(trajectory)
# result.drift_rate: 意图漂移率
```

#### 5. 增强评估器 (assert_code/multi_turn_enhanced_evaluator.py)
```python
from assert_code.multi_turn_enhanced_evaluator import MultiTurnEnhancedEvaluator

evaluator = MultiTurnEnhancedEvaluator()
result = evaluator.evaluate(case_info, round_rows)
# result['enhanced_pass']: 综合通过状态
# result['llm_judge_result']: LLM Judge评估结果
# result['state_validation_result']: 状态转移验证结果
# result['consistency_result']: 信息一致性检查结果
```

#### 6. 批量断言 (assert_code/batch_model_assert.py)
```python
from assert_code.batch_model_assert import BatchModelAssert

batch = BatchModelAssert(model_name='deepseek-v4-pro', max_group_size=10)
results = batch.batch_evaluate(items)
summary = batch.generate_report(items, results, output_dir='./report')
```

### 公共模块

#### 7. 模型HTTP操作 (common/modelHttpAction.py)
- `ModelHttpAction` - 封装外部模型API调用（支持 DeepSeek、Kimi 等）
- `chat(prompt, system_prompt, max_tokens)` - 通用对话接口
- `chat_with_json_output(prompt, json_schema, system_prompt)` - 结构化JSON输出接口

#### 8. 批量数据收集器 (utils/batch_assert_collector.py)
- `BatchAssertCollector` - 线程安全的批量断言数据收集器（单例模式）
- `add(item)` - 收集单条测试数据
- `get_all()` - 获取所有收集的数据
- `save_to_file(filepath)` / `load_from_file(filepath)` - 持久化/恢复

#### 9. 测试用例处理 (utils/handle_model_cases.py)
- `assemble_model_case_params(case_type)` - 组装模型测试用例参数
- `filter_model_cases(env, group, case_type)` - 按条件筛选测试用例

## 环境配置

### 测试环境配置方式

本项目提供两种方式配置测试环境：

#### 方式一：在代码中直接设置（推荐）

打开 `exec_pytest.py` 文件，在 main 函数中修改 `env` 和 `group` 变量：

```python
if __name__ == '__main__':
    # 直接修改这两行来设置测试环境
    env = 'pro'      # 可选: 'stable', 'yn_stable', 'mxg_stable', 'yn_pro', 'mxg_pro', 'pro'
    group = 'default'    # 可选: 'stable', 'project_109111228', 'project_10963208', 'default'
```

#### 方式二：修改配置文件

配置文件位置：`config/env_group_config.yaml`

```yaml
env: pro
group: default
```

### 支持的测试环境

| 环境 | 分组 | 说明 | 支持的断言方式 |
|------|------|------|----------------|
| stable | stable | 国内稳定环境 | MySQL数据库断言 |
| yn_stable | project_109111228 | 印尼稳定环境 | ClickHouse断言 |
| mxg_stable | project_10963208 | 墨西哥稳定环境 | ClickHouse断言 |
| yn_pro | default | 印尼生产环境 | 接口断言 |
| mxg_pro | default | 墨西哥生产环境 | 接口断言 |
| pro | default | 生产环境 | 接口断言 |

### 模型测试环境变量

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MODEL_BATCH_ASSERT` | `0` | 启用批量断言模式（`1`启用） |
| `MODEL_BATCH_JUDGE_MODEL` | `deepseek-v4-pro` | 批量断言评判模型 |
| `MODEL_BATCH_MAX_GROUP_SIZE` | `10` | 单轮批量每组最大数量 |
| `MODEL_BATCH_MAX_GROUP_SIZE_MULTI` | `2` | 多轮批量每组最大数量 |
| `MODEL_MULTI_TURN_PASS_THRESHOLD` | `70` | 多轮评估通过阈值 |
| `MODEL_LOCAL_ASSERT_STRICT_MODE` | `1` | 本地断言严格模式（`1`一票否决，`0`比例通过） |
| `MODEL_LOCAL_ASSERT_PER_ROUND` | `1` | 是否逐轮检查本地断言 |
| `MODEL_LOCAL_ASSERT_MAX_FAIL_RATIO` | `0.0` | 宽松模式下允许的最大失败比例 |
| `MODEL_ENHANCED_MULTI_TURN_EVAL` | `0` | 启用多轮增强评估（`1`启用） |
| `MODEL_ENHANCED_LLM_JUDGE_MODEL` | `kimi-k2.6` | 增强评估LLM模型 |

## 依赖安装

### 一键安装所有依赖

```bash
pip install -r requirements.txt
```

### 国内镜像加速安装（推荐）

```bash
# 使用清华镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或使用阿里云镜像源
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### 主要依赖包及版本

**测试框架**
- `pytest==7.4.3` - Python测试框架
- `allure-pytest==2.13.2` - Allure测试报告插件

**数据验证**
- `jsonschema==4.20.0` - JSON Schema验证工具

**数据处理**
- `pandas==2.0.3` - 数据分析和处理库
- `openpyxl==3.1.2` - Excel文件读写库

**数据库连接**
- `pymysql==1.1.0` - MySQL数据库连接驱动
- `sqlalchemy==2.0.23` - Python SQL工具包和ORM框架

**分布式协调**
- `kazoo==2.9.0` - Zookeeper客户端库

**HTTP请求**
- `requests==2.31.0` - HTTP请求库
- `urllib3==2.1.0` - HTTP客户端库

**日志处理**
- `loguru==0.7.2` - 简化的日志记录库

**配置文件处理**
- `pyyaml==6.0.1` - YAML文件解析库

**工具库**
- `prettytable==3.9.0` - 表格美化输出库
- `jsonpath==0.82` - JSON路径查询库

**其他依赖**
- `typing-extensions==4.9.0` - 类型提示扩展库

## 使用说明

### 1. 配置测试环境

在运行测试前，先配置测试环境（参考上面的"环境配置"章节）。

### 2. 执行测试

#### 方式一: 直接运行主文件（推荐）
```bash
python exec_pytest.py
```
程序会自动：
- 读取配置并更新 `config/env_group_config.yaml`
- 执行测试用例
- 生成 Allure 测试报告
- 启动 Allure 本地报告服务
- 统计通过/失败用例数、执行日期、env、group 和自动化用例通过率
- 通过企业微信 webhook 发送报告摘要和 Allure 报告地址到对应群聊

#### 方式二: 使用pytest命令

**执行决策引擎测试：**
```bash
# 执行所有测试
pytest test_cases/ -s --alluredir ./report/tmp --clean-alluredir

# 按标记执行
pytest -m process -s --alluredir ./report/tmp --clean-alluredir
pytest -m package -s --alluredir ./report/tmp --clean-alluredir
pytest -m feature_platform -s --alluredir ./report/tmp --clean-alluredir
```

**执行模型意图识别测试：**
```bash
# 执行模型意图识别测试（单轮+多轮）
pytest test_cases/test_model_intent_recognition.py -s --alluredir ./report/tmp --clean-alluredir

# 只执行多轮对话测试
pytest test_cases/test_model_intent_recognition.py -m model_multi_turn -s --alluredir ./report/tmp --clean-alluredir

# 只执行单轮测试
pytest test_cases/test_model_intent_recognition.py -m model_intent -s --alluredir ./report/tmp --clean-alluredir
```

#### 方式三: 调试单个用例

```bash
# 调试单个用例（通过环境变量指定case_id）
python debug_model_by_pytest.py
```

### 3. 查看测试报告

#### 生成Allure报告
```bash
allure generate ./report/tmp -o ./report/report --clean
```

#### 启动Allure服务查看报告
```bash
allure open ./report/report
```

#### 批量断言报告
启用批量断言模式（`MODEL_BATCH_ASSERT=1`）后，报告会自动生成在：
- `report/model_intent_recognition/batch_assert_single_report_{timestamp}.html` - 单轮批量断言报告
- `report/model_intent_recognition/batch_assert_multi_turn_report_{timestamp}.html` - 多轮批量断言报告
- `report/model_intent_recognition/batch_assert_single_detail_{timestamp}.csv` - 单轮详细结果
- `report/model_intent_recognition/batch_assert_multi_turn_detail_{timestamp}.csv` - 多轮详细结果

#### 执行完成后的自动通知
运行 `python exec_pytest.py` 后，框架会自动读取 Allure 汇总信息，并通过 `utils/handle_allure_report.py` 将以下内容发送到对应企微群：
- 执行日期
- 当前执行环境 `env`
- 当前执行分组 `group`
- 通过用例数
- 失败用例数
- 自动化用例通过率
- Allure 报告访问地址

说明：Allure 报告地址为当前执行机器启动的本地服务地址，需确保接收人可以访问该机器对应 IP 和端口。

## Pytest标记说明

### 流程引擎标记
- `process` - 流程引擎测试
- `process_online` - 在线实时决策
- `process_batch` - 离线批跑决策

### 米霍克引擎标记
- `package` - 米霍克引擎测试
- `package_online_exec_rcflow_decision` - 在线流程决策
- `package_online_exec_make_decision` - 在线节点决策
- `package_online_exec_package_decision` - 在线乐包决策
- `package_batch_exec_rcflow_decision` - 批跑流程决策
- `package_batch_exec_make_decision` - 批跑节点决策
- `package_batch_exec_package_decision` - 批跑乐包决策
- `package_simulate_exec_rcflow_decision` - 仿真流程决策

### 特征平台标记
- `feature_platform` - 特征平台测试
- `feature_field_batch` - 授信代理层字段批量拉取
- `feature_ruleengine_proxy` - 交易代理层字段获取
- `feature_simulate_proxy` - 仿真代理层字段获取
- `feature_business_proxy` - 业务代理层字段获取
- `feature_offline_proxy` - 离线代理层字段获取

### 模型意图识别标记
- `model_intent` - 模型意图识别测试（单轮）
- `model_multi_turn` - 多轮对话测试
- `model_checklist` - 检查清单模式测试

## 测试用例编写规范

### 用例数据格式 (Excel)

测试用例数据存储在 `case_data/` 目录下的Excel文件中，需包含以下列:
- **场景**: 测试场景描述
- **类型**: 决策类型（如 execute_online, execute_batch等）
- **入参**: Python字典格式的入参数据
- **预期结果**: Python字典格式的预期结果

### 意图识别用例格式

多轮对话测试用例需要包含以下列：
- **case_id**: 用例唯一标识
- **case_desc**: 用例描述
- **intent**: 意图分类
- **questions**: 多轮用户问题（JSON列表）
- **expected_answers**: 期望的模型回复（JSON列表）
- **round_intents**: 每轮期望的意图分类
- **similarity_threshold**: 语义相似度阈值

### 断言机制

#### 决策引擎断言
1. **接口返回断言**: 验证接口返回的结果结构和字段值
2. **数据库断言**: 在stable环境下验证MySQL数据库中的数据
3. **ClickHouse断言**: 在yn_stable和mxg_stable环境下验证ClickHouse数据

#### 模型意图识别断言
1. **意图分类断言**: 验证模型识别的意图是否正确
2. **语义相似度断言**: 对比模型回复与标准答案的语义相似度（外部模型评判）
3. **ASSET卡片断言**: 验证业务参数卡片是否符合预期
4. **转人工断言**: 验证会话类型（NORMAL/TRANSFER）是否正确
5. **上下文继承断言**: 验证模型是否继承了前文上下文
6. **意图污染断言**: 验证模型是否混入了旧话题信息
7. **风险拒答断言**: 验证模型是否对风险问题正确拒答

## 注意事项

1. **环境依赖**: stable环境可以直连数据库进行DB断言，其他环境需要根据实际情况调整
2. **延迟等待**: 印尼环境(yn_stable)和墨西哥环境(mxg_stable)的ClickHouse数据同步存在延迟，测试中会等待90-180秒
3. **用例配置**: 测试环境配置在 `config/env_group_config.yaml` 文件中管理，也可以直接在 `exec_pytest.py` 的 main 函数中修改
4. **日志输出**:
   - 使用 loguru 框架记录日志，所有日志带有时间戳
   - 执行测试时需要加 `-s` 参数才能看到日志输出
   - 日志格式: `2026-01-08 16:15:47.270 | INFO | 日志信息`
5. **配置更新**: 在 `exec_pytest.py` 中修改 env 或 group 后运行，配置会自动保存到配置文件
6. **避免重复日志**: `get_test_config()` 函数在正常情况下不打印日志，只在异常时打印警告
7. **模型测试注意**: 外部模型评判依赖三方模型API，请确保网络通畅且API Token有效

## 作者信息

- **Author**: jeremyzhai
- **Date**: 2024-08-13

## 更新日志

- **2024-08-13**: 创建流程引擎测试模块
- **2024-08-14**: 添加pytest执行入口和用例处理工具
- **2024-08-16**: 添加米霍克引擎测试模块
- **2025-06-20**: 添加特征平台测试模块
- **2026-01-08**:
  - 优化测试环境配置管理
  - 配置文件从根目录迁移到 `config/env_group_config.yaml`
  - 支持在代码中直接设置环境，自动更新配置文件
  - 统一使用 loguru 日志框架替换 print
  - 优化日志输出，避免重复打印
  - 新增详细使用指南文档
- **2026-05-20**:
  - 新增模型意图识别自动化测试模块（单轮测试）
  - 集成外部模型评判（LLM-as-Judge）
  - 支持语义相似度评估和细粒度检查清单
  - 新增意图知识库和检查清单配置
- **2026-06-02**:
  - 新增多轮对话质量评估器（MultiTurnLLMJudge）
  - 支持 G1/G2 底线检查 + Q1-Q5 质量评分
  - 新增会话状态转移验证器（SessionStateValidator）
  - 新增多轮对话增强评估器（MultiTurnEnhancedEvaluator）
- **2026-06-09**:
  - 新增批量断言策略（单轮/多轮）
  - 支持批量模式生成 CSV + HTML 报告
  - 新增雷达图可视化
  - 新增意图混淆矩阵分析工具
  - 优化本地断言（转人工 + ASSET）按轮展示
  - 多轮报告中本地断言列支持按轮次详细展示
- **2026-06-12**:
  - 优化多轮对话数值一致性评判逻辑
  - 标准答案中的金额/利率等数字不再与模型输出死板对比
  - 评判关注模型输出数值在上下文中的自洽性和与用户诉求的对应性
  - 优化 CSV/HTML 报告中本地断言的展示方式
