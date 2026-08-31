# 鏍稿績妯″潡 鈥?PR-Review Agent

PR-Review Agent 鐨勫熀纭€璁炬柦灞傦紝涓轰笂灞備笟鍔℃彁渚涢€氱敤鑳藉姏銆?

## 妯″潡娓呭崟

| 鏂囦欢 | 鍔熻兘 | 璇存槑 |
|------|------|------|
| config_loader.py | 閰嶇疆鍔犺浇鍣?| 缁熶竴鍔犺浇 .env + settings.yaml锛屾敮鎸佺幆澧冨彉閲忔浛鎹€佺绾挎ā寮忔娴?|
| git_ops.py | Git 鎿嶄綔灏佽 | 鍙 Git 鎿嶄綔锛歞iff銆佹枃浠跺唴瀹广€佸彉鏇村垪琛紝鏀寔 hash/鍒嗘敮/HEAD~N |
| file_utils.py | 鏂囦欢宸ュ叿 | 瀹夊叏鏂囦欢璇诲啓锛屾敮鎸佽矾寰勭櫧鍚嶅崟绾︽潫锛岄槻姝㈣秺鏉冭闂?|
| serializer.py | 搴忓垪鍖栧伐鍏?| JSON/JSONL 搴忓垪鍖栵紝鏀寔 datetime銆丳ath 绛夎嚜瀹氫箟绫诲瀷 |
| logger.py | 鏃ュ織宸ュ叿 | 鍩轰簬 transcript.jsonl 鐨勬棩蹇楄褰曪紝鏀寔 AGENT_ACTION 鑷畾涔夌骇鍒?|

## 浣跨敤绀轰緥

### 閰嶇疆鍔犺浇
```python
from src.core.config_loader import get_config
config = get_config()
mimo_url = config.get("model.mimo.api_url")
is_offline = config.offline_mode
```

### Git 鎿嶄綔
```python
from src.core.git_ops import GitOps
ops = GitOps("/path/to/repo")
diff = ops.get_diff("main", "feature-branch")
files = ops.list_changed_files("HEAD~3", "HEAD")
content = ops.get_file_content("HEAD", "src/main.py")
```

### 鏃ュ織璁板綍
```python
from src.core.logger import get_logger
logger = get_logger("task-abc-123")
logger.info("system", "浠诲姟寮€濮?)
logger.agent_action("scanner_agent", "璋冪敤 search_code", {"keyword": "password"})
```

### 搴忓垪鍖?
```python
from src.core.serializer import to_json, from_json, save_json, load_json
json_str = to_json({"created_at": datetime.now()})
data = from_json(json_str)
save_json("output/result.json", data)
```

## 璁捐鍘熷垯
- **鍙绾︽潫**锛歡it_ops 鎵€鏈夋搷浣滃潎涓哄彧璇伙紝缁濅笉淇敼浠撳簱
- **璺緞瀹夊叏**锛歠ile_utils 鏀寔鐧藉悕鍗曠害鏉燂紝闃叉瓒婃潈璁块棶
- **浠诲姟闅旂**锛歭ogger 鎸?task_id 闅旂鏃ュ織鏂囦欢
- **鑷姩闄嶇骇**锛歝onfig_loader 鑷姩妫€娴?API 瀵嗛挜缂哄け锛屽垏鎹㈢绾挎ā寮?

