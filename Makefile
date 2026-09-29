.PHONY: help install seed dev test migrate backup tunnel reset clean

PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip

help:
	@echo "make install  建立虛擬環境並安裝依賴"
	@echo "make seed     建表並灌入示範資料（已有的話略過）"
	@echo "make reset    清空資料庫重新灌入"
	@echo "make dev      開發模式啟動（自動重載）"
	@echo "make serve    正式模式啟動（讀 backend/.env）"
	@echo "make test     跑測試（需服務已啟動）"
	@echo "make migrate  套用資料庫遷移（alembic upgrade head）"
	@echo "make backup   熱備份資料庫到 backups/"
	@echo "make tunnel   開 Cloudflare 對外通道"
	@echo "make clean    清掉虛擬環境與快取"

install:
	python3 -m venv backend/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt
	@echo "完成。接著跑 make seed 與 make dev"

seed:
	cd backend && .venv/bin/python -m app.seed

reset:
	cd backend && .venv/bin/python -m app.seed --reset

dev:
	cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000

serve:
	./scripts/serve.sh

test:
	bash backend/tests/smoke.sh
	bash backend/tests/features.sh
	bash backend/tests/ratelimit.sh
	$(PY) backend/tests/test_ratelimit_redis.py

migrate:
	cd backend && .venv/bin/alembic upgrade head

backup:
	python3 scripts/backup.py

tunnel:
	./scripts/tunnel.sh

check:
	$(PY) -m compileall -q backend/app && echo "語法檢查通過"

clean:
	rm -rf backend/.venv backend/app/__pycache__ backend/app/routers/__pycache__ backend/logs
