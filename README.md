# MoviePilot（站点认证解锁 · 自用补丁叠加）

> 仅供个人自托管与学习研究使用。本仓库**不含上游源码**，只维护一个体积极小的补丁与
> CI 流水线：每天自动拉取上游 [`jxxghp/MoviePilot@v2`](https://github.com/jxxghp/MoviePilot)
> 最新源码，叠加补丁后构建 Docker 镜像并推送到 Docker Hub。

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

CI（[`.github/workflows/build.yml`](.github/workflows/build.yml)）每天：

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
