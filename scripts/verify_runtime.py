"""在隔离容器中验证 v3 站点扩展的实际认证结果，不访问外部站点。"""

import importlib
import os
import pathlib
import sys
import tempfile


def check_sites():
    """检查真实扩展的认证结果、索引和重复补丁调用。"""
    module = importlib.import_module("app.application.site.sites")
    helper = module.SitesHelper()
    level = helper.auth_level
    if level != 2:
        raise RuntimeError(f"v3 authentication verification failed: auth_level={level!r}")
    # 临时数据库没有已配置站点，get_indexers() 允许为空；检查内置资源目录。
    indexers = helper.get_indexsites()
    if not indexers:
        raise RuntimeError("v3 authentication level is 2 but built-in site catalog is empty")
    patcher = importlib.import_module("app.application.site._sites_unlock")
    extension = pathlib.Path(module.__file__)
    before = extension.read_bytes()
    patcher.install()
    if extension.read_bytes() != before:
        raise RuntimeError("Repeated installation changed the extension")
    print(f"PASS: {module.__name__}, auth_level={level}, catalog_entries={len(indexers)}, repeated installation unchanged")


def main():
    """使用真实临时 SQLite 和事务端口验证扩展，不启动完整应用。"""
    sys.path.insert(0, "/app")
    with tempfile.TemporaryDirectory(prefix="moviepilot-overlay-") as directory:
        os.environ["CONFIG_DIR"] = directory
        os.environ["DB_TYPE"] = "sqlite"
        from app.db.base import Base
        from app.db.engine import get_engine
        from app.db.models import load_all_models
        from app.db.session import SessionFactory, async_session_scope
        from app.db.adapters.transaction import TransactionalWriteRunner
        from app.db.uow import transaction_runner_scope

        load_all_models()
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        runner = TransactionalWriteRunner(sync_session=SessionFactory, async_session=async_session_scope)
        from app.application.site.protocol import configure_site_protocol_port, reset_site_protocol_port
        from app.modules.indexer import IndexerModule

        # 直接装配真实索引模块的静态协议实现，不启动整套模块发现及网络任务。
        configure_site_protocol_port(IndexerModule)
        try:
            with transaction_runner_scope(sync=runner.sync, async_=runner.async_):
                check_sites()
        finally:
            reset_site_protocol_port()
            engine.dispose()


if __name__ == "__main__":
    main()
