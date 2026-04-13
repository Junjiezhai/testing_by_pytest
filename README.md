# 决策引擎自动化测试框架

## 项目简介

本项目是一个基于 pytest 的自动化测试框架，用于测试决策引擎系统。主要覆盖流程引擎、米霍克决策引擎和特征平台三大模块的功能测试。

## 项目结构

```
making_decison_test/
├── test_cases/              # 测试用例目录
│   ├── test_process_engine.py      # 流程引擎测试用例
│   ├── test_mihawk_engine.py       # 米霍克引擎测试用例
│   └── test_feature_platform.py    # 特征平台测试用例
│
├── script_code/             # 执行脚本目录
│   ├── process_engine_exec.py           # 流程引擎执行脚本
│   ├── mihawk_engine_exec.py            # 米霍克引擎执行脚本
│   ├── feature_platform_exec.py         # 特征平台执行脚本
│   ├── postloan_touch_platform_exec.py  # 贷后触达平台执行脚本
│   └── offer_service_exec.py            # Offer服务执行脚本
│
├── common/                  # 公共模块目录
│   ├── baseRpc.py          # RPC基础类
│   ├── rpcAction.py        # RPC操作封装
│   ├── dbAction.py         # 数据库操作封装
│   ├── ckAction.py         # ClickHouse操作封装
│   ├── httpAction.py       # HTTP请求操作封装
│   ├── riskMock.py         # 风控Mock
│   └── postLoanAction.py   # 贷后操作封装
│
├── utils/                   # 工具模块目录
│   ├── handle_yaml.py      # YAML文件处理工具
│   ├── handle_log.py       # 日志处理工具（基于loguru）
│   ├── handle_path.py      # 路径处理工具
│   ├── handle_cases.py     # 测试用例处理工具
│   ├── handle_instanceid.py # 实例ID处理工具
│   └── handle_allure_report.py # Allure报告统计与企微通知工具
│
├── assert_code/             # 断言模块目录
│   ├── assertAction.py     # 断言操作类
│   └── assert_decorators.py # 断言装饰器
│
├── config/                  # 配置文件目录
│   ├── env_group_config.yaml         # 测试环境配置文件（env和group）
│   ├── process_para_format.yaml      # 流程引擎参数格式配置
│   ├── package_para_format.yaml      # 乐包引擎参数格式配置
│   ├── feature_para_format.yaml      # 特征平台参数格式配置
│   ├── execute_res_schema.yaml       # 执行结果Schema配置
│   └── execute_res_db_assert.yaml    # 执行结果数据库断言配置
│
├── case_data/               # 测试用例数据目录
│   ├── pro_process_test_cases.xlsx        # 生产环境流程测试用例
│   ├── pro_package_test_cases.xlsx        # 生产环境乐包测试用例
│   ├── pro_feature_test_cases.xlsx        # 生产环境特征测试用例
│   ├── yn_stable_process_test_cases.xlsx  # 印尼稳定环境流程测试用例
│   ├── yn_stable_package_test_cases.xlsx  # 印尼稳定环境乐包测试用例
│   ├── yn_stable_feature_test_cases.xlsx  # 印尼稳定环境特征测试用例
│   ├── yn_pro_process_test_cases.xlsx     # 印尼生产环境流程测试用例
│   ├── yn_pro_package_test_cases.xlsx     # 印尼生产环境乐包测试用例
│   ├── yn_pro_feature_test_cases.xlsx     # 印尼生产环境特征测试用例
│   ├── stable_process_test_cases.xlsx     # 国内稳定环境流程测试用例
│   ├── stable_package_test_cases.xlsx     # 国内稳定环境乐包测试用例
│   └── stable_feature_test_cases.xlsx     # 国内稳定环境特征测试用例
│
├── report/                  # 测试报告目录
│   ├── tmp/                # Allure临时数据
│   └── report/             # Allure测试报告
│
├── exec_pytest.py          # pytest执行入口文件
├── pytest.ini              # pytest配置文件
├── requirements.txt        # 项目依赖文件
├── README.md               # 项目说明文档
└── 使用指南.md             # 详细使用指南
```

## 测试模块说明

### 1. 流程引擎测试 (test_process_engine.py)
测试流程引擎的在线实时决策和离线批跑决策功能
- **在线实时决策**: 执行在线决策并验证结果
- **离线批跑决策**: 执行批量决策并验证结果（已注释）

### 2. 米霍克引擎测试 (test_mihawk_engine.py)
测试米霍克决策引擎的多种决策模式
- **流程决策**: 在线/批跑/仿真模式的流程决策（部分已注释）
- **节点决策**: 在线/批跑模式的节点决策
- **乐包决策**: 在线/批跑模式的乐包决策

### 3. 特征平台测试 (test_feature_platform.py)
测试特征平台的字段计算功能
- **授信代理层**: 字段批量拉取
- **交易代理层**: 字段获取
- **仿真代理层**: 字段获取
- **业务代理层**: 字段获取
- **离线代理层**: 字段获取

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

修改后运行 `python exec_pytest.py`，配置会自动保存到配置文件中。

**示例 1: 切换到印尼稳定环境**
```python
env = 'yn_stable'
group = 'project_109111228'
```

**示例 2: 切换到墨西哥稳定环境**
```python
env = 'mxg_stable'
group = 'project_10963208'
```

**示例 3: 切换到国内稳定环境**
```python
env = 'stable'
group = 'stable'
```

#### 方式二：修改配置文件

配置文件位置：`config/env_group_config.yaml`

```yaml
env: pro
group: default
```

直接修改配置文件中的 `env` 和 `group` 值即可。配置文件会在运行时被自动读取。

### 支持的测试环境
- `stable`: 稳定环境（支持MySQL数据库断言）
- `yn_stable`: 印尼稳定环境（支持ClickHouse断言）
- `mxg_stable`: 墨西哥稳定环境（支持ClickHouse断言）
- `yn_pro`: 印尼生产环境
- `mxg_pro`: 墨西哥生产环境
- `pro`: 生产环境

### 环境与分组对应关系

| 环境 | 分组 | 说明 | 支持的断言方式 |
|------|------|------|----------------|
| stable | stable | 国内稳定环境 | MySQL数据库断言 |
| yn_stable | project_109111228 | 印尼稳定环境 | ClickHouse断言 |
| mxg_stable | project_10963208 | 墨西哥稳定环境 | ClickHouse断言 |
| yn_pro | default | 印尼生产环境 | 接口断言 |
| mxg_pro | default | 墨西哥生产环境 | 接口断言 |
| pro | default | 生产环境 | 接口断言 |

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
```bash
# 执行所有测试
pytest test_cases/ -s --alluredir ./report/tmp --clean-alluredir

# 按标记执行
pytest -m process -s --alluredir ./report/tmp --clean-alluredir
pytest -m package -s --alluredir ./report/tmp --clean-alluredir
pytest -m feature_platform -s --alluredir ./report/tmp --clean-alluredir

# 执行特定测试文件
pytest test_cases/test_process_engine.py -s --alluredir ./report/tmp
pytest test_cases/test_feature_platform.py -s --alluredir ./report/tmp
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

### 4. 运行效果示例

```
2026-01-08 16:15:47.270 | INFO | ================================================================================
2026-01-08 16:15:47.270 | INFO | pytest 测试执行器
2026-01-08 16:15:47.270 | INFO | ================================================================================
2026-01-08 16:15:47.271 | INFO | 正在更新配置文件...
2026-01-08 16:15:47.271 | INFO |   env: pro
2026-01-08 16:15:47.271 | INFO |   group: default
2026-01-08 16:15:47.280 | INFO | 配置文件更新成功: env='pro', group='default'
2026-01-08 16:15:47.280 | INFO | --------------------------------------------------------------------------------
2026-01-08 16:15:47.280 | INFO | 当前测试配置:
2026-01-08 16:15:47.280 | INFO |   环境 (env)  : pro
2026-01-08 16:15:47.280 | INFO |   分组 (group): default
2026-01-08 16:15:47.280 | INFO | --------------------------------------------------------------------------------
2026-01-08 16:15:47.280 | INFO |
开始执行测试...
```

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

## 测试用例编写规范

### 用例数据格式 (Excel)
测试用例数据存储在 `case_data/` 目录下的Excel文件中，需包含以下列:
- **场景**: 测试场景描述
- **类型**: 决策类型（如 execute_online, execute_batch等）
- **入参**: Python字典格式的入参数据
- **预期结果**: Python字典格式的预期结果

### 断言机制
测试框架支持多层级断言:
1. **接口返回断言**: 验证接口返回的结果结构和字段值
2. **数据库断言**: 在stable环境下验证MySQL数据库中的数据
3. **ClickHouse断言**: 在yn_stable和mxg_stable环境下验证ClickHouse数据

## 核心功能类

### 1. 配置管理 (utils/handle_yaml.py)
- `get_test_config()` - 读取测试环境配置文件 `config/env_group_config.yaml`
- `update_test_config(env, group)` - 更新测试环境配置文件
- `read_yaml_data(file_dir)` - 读取指定yaml文件内容

### 2. 日志管理 (utils/handle_log.py)
- 基于 `loguru` 框架实现
- 统一的日志输出格式，带时间戳
- 使用方式: `from utils.handle_log import log` 然后 `log.info("消息")`

### 3. 用例处理 (utils/handle_cases.py)
- `filter_rows_by_type(xlsx_name, target_type)` - 从Excel读取指定类型的用例
- `assemble_case_params(engine_type, exec_type)` - 组装pytest参数化用例，自动从配置文件获取env和group
- `get_case_desc(engine_type, exec_type)` - 获取用例描述，自动从配置文件获取env

### 4. 断言类 (assert_code/assertAction.py)
- `value_assert(data, assert_rules, desc)` - 值断言，支持精确匹配和JsonPath表达式

### 5. RPC操作类 (common/baseRpc.py, common/rpcAction.py)
- 封装RPC调用逻辑
- 支持Zookeeper服务发现
- 自动生成trace_id

### 6. 数据库操作类 (common/dbAction.py, common/ckAction.py)
- MySQL数据库查询操作 (DbAction)
- ClickHouse数据库查询操作 (CkAction)
- 支持上下文管理器

### 7. 主入口函数 (exec_pytest.py)
- `set_test_config(env, group)` - 设置测试配置并更新配置文件
  - 接收 env 和 group 参数
  - 自动更新 `config/env_group_config.yaml` 文件
  - 返回当前生效的配置字典

### 8. Allure报告通知工具 (utils/handle_allure_report.py)
- `get_case_count(summary_path)` - 从 Allure 的 `summary.json` 统计通过数和失败数
- `open_allure_report(report_dir)` - 启动 Allure 报告服务并返回访问地址
- `report_summary(num_successd, num_failed, allure_report_url, env, group)` - 将执行日期、env、group、通过数、失败数、通过率和报告地址通过企微 webhook 发送到群聊

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
