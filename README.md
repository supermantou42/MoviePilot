# MoviePilot（站点认证解锁 · 自用补丁叠加）

> 仅供个人自托管与学习研究使用。本仓库**不含上游源码**，只维护一个体积极小的补丁与
> CI 流水线：构建时拉取上游 [`jxxghp/MoviePilot@v2`](https://github.com/jxxghp/MoviePilot)
> 最新源码，叠加补丁后构建 Docker 镜像并推送到 Docker Hub。

## V3 迁移

新增独立工作流 **Build patched v3 image**（`.github/workflows/build-v3.yml`），
跟随上游 `v3` 分支，镜像发布为 `DOCKER_USERNAME/moviepilot-v3`，不覆盖原 V2 镜像。
每天香港时间 02:45 构建，也可在 Actions 手动触发；复用原有两个 Docker Hub Secrets。
工作流先解析并固定后端、插件与资源提交，再构建、执行离线认证和索引检查，
检查通过后才推送；系统更新层按周刷新，避免长期复用旧系统软件包缓存。

`scripts/apply_patch.sh` 会识别 V2 的 `app/helper` 和 V3 的 `app/application/site`，
在实际站点包导入前运行共享补丁，并为 Playwright Node 驱动安装 `libatomic1`。
V3 使用标准 Python 运行时，只支持 `linux/amd64`；尚不支持 ARM64、Windows 或 V3t。
补丁依赖已知 Cython 函数符号和 x86-64 指令结构，上游资源变化后必须重新验证。

本地检查：

```bash
python -m unittest discover -s tests -v
bash scripts/apply_patch.sh upstream
docker build -f upstream/docker/Dockerfile -t moviepilot-v3-overlay:local upstream
docker run --rm --network none --entrypoint /opt/venv/bin/python \
  -e CONFIG_DIR=/tmp/moviepilot-overlay-check \
  -v "$PWD/scripts/verify_runtime.py:/verify_runtime.py:ro" \
  moviepilot-v3-overlay:local /verify_runtime.py
```

V3 会迁移数据库与配置，请使用 V2 配置目录的备份副本验证，不能让两个实例共用配置目录。
上游版本变化说明见 [V2 到 V3](https://github.com/jxxghp/MoviePilot/blob/v3/docs/v2-to-v3-overview.md)。

## 这个补丁做了什么

上游的「站点认证（AUTH_SITE / 用户认证）」会在你未通过 PT 站点认证时，锁住站点搜索 /
索引等功能。本补丁针对 Cython 编译扩展 `app/helper/sites.*.so`，在容器**运行时**就地把
内部 `get_auth_level` 的返回恒定为等级 2，从而解锁这些功能。补丁具有以下性质：

- **自愈**：上游资源更新重新下载未打补丁的 `.so` 后，下次启动会自动重新打上。
- **与偏移无关**：通过 ELF 符号表定位函数，再在函数体内识别 `number_tab` 相邻两项的
  `mov rax,[rip+disp32]` 加载，将未认证项重指向已认证项。
- **幂等、失败安全**：已打补丁或结构不符合预期时不做任何改动，绝不影响正常启动。

实现见 [`patch/app/helper/_sites_unlock.py`](patch/app/helper/_sites_unlock.py)，
通过 [`scripts/apply_patch.sh`](scripts/apply_patch.sh) 叠加到上游 `app/helper/__init__.py`。

## 工作方式（Overlay 重建）

CI（[`.github/workflows/build.yml`](.github/workflows/build.yml)）由手动或代码推送触发，定时构建已关闭：

1. 解析上游 `v2` 分支最新提交，若与上次构建相同则跳过（节省额度）；
2. 检出上游源码 → 运行 `apply_patch.sh` 叠加补丁；
3. 用上游 `docker/Dockerfile` 构建镜像；
4. 推送到 `DOCKER_USERNAME/moviepilot`，打 `latest` / `<版本>` / `<版本>-<短SHA>` 标签。

手动触发（Actions → Run workflow）会忽略未变更检测强制重建。

## 使用前置：配置 Secrets

在仓库 **Settings → Secrets and variables → Actions** 添加：

| Secret | 说明 |
| --- | --- |
| `DOCKER_USERNAME` | Docker Hub 用户名 |
| `DOCKER_PASSWORD` | Docker Hub 访问令牌（Account Settings → Security → New Access Token，Read/Write 权限） |

## 运行镜像

```bash
docker run -d \
  --name moviepilot \
  -p 3000:3000 \
  -v /path/to/config:/config \
  -e SUPERUSER=admin \
  <DOCKER_USERNAME>/moviepilot:latest
```

配置项与上游完全一致，参见 [上游文档](https://wiki.movie-pilot.org)。

### 自动更新（可选）

用 [Watchtower](https://containrrr.dev/watchtower/) 跟随镜像更新：

```bash
docker run -d --name watchtower \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower --cleanup --interval 86400 moviepilot
```

## 致谢与许可

上游项目 [MoviePilot](https://github.com/jxxghp/MoviePilot) 版权与许可归原作者所有
（见仓库 [`LICENSE`](https://github.com/jxxghp/MoviePilot/blob/v2/LICENSE)）。本仓库为
个人学习研究用途的补丁叠加，请遵守上游许可与所在地区法律法规，自行承担使用风险。
