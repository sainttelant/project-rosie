# 基于个人 GitHub 账号 Fork & Push 操作说明

> 适用场景：从 GitHub 上 clone 一个**别人的 public 仓库**，想基于它做修改，
> 然后推送到**你自己（个人账号 `sainttelant`）fork 出来的仓库**，最后可以发 Pull Request。
>
> 本文档基于本机已配置好的**双账号 SSH** 环境（见文末「附录：本机双账号配置」）。

---

## 0. 前置：本机的双账号约定

本机 `~/.ssh/config` 里配置了两个别名，**看 remote 前缀就知道用哪个账号**：

| 别名 | 对应账号 | 用途 |
|------|----------|------|
| `github.com`（默认） | 公司账号 `wilson-xue_magna` | 公司组织下的仓库 |
| `github-personal` | 个人账号 `sainttelant` | 个人仓库 / fork |

> ⚠️ 关键规则：**凡是推送到个人账号的仓库，remote 必须用 `git@github-personal:...` 前缀**，
> 否则会走公司 key，导致 `Permission denied`。

---

## 1. 标准流程（推荐：先 Fork 再 Clone）

这是最干净的做法，避免后面来回改 remote。

### 步骤 1：在 GitHub 网页上 Fork

1. 打开目标仓库页面，例如 `https://github.com/原作者/some-repo`
2. 点右上角 **`Fork`** 按钮
3. 选择 fork 到你的**个人账号 `sainttelant`** 名下
4. Fork 完成后，你的仓库地址是：
   ```
   https://github.com/sainttelant/some-repo
   ```

### 步骤 2：Clone 你自己的 fork（用个人别名）

```bash
git clone git@github-personal:sainttelant/some-repo.git
cd some-repo
```

> 注意这里用的是 `git@github-personal:` 前缀，走个人 key。

### 步骤 3：把原作者仓库加为 `upstream`（用于以后同步更新）

```bash
git remote add upstream git@github.com:原作者/some-repo.git
git remote -v
```

此时 remote 应该是这样：

```
origin     git@github-personal:sainttelant/some-repo.git   (你的 fork，推这里)
upstream   git@github.com:原作者/some-repo.git             (原仓库，从这里拉更新)
```

### 步骤 4：建分支、改代码、推送

```bash
git checkout -b my-feature        # 建一个功能分支
# ... 改代码 ...
git add .
git commit -m "feat: 我的改动"
git push origin my-feature        # 推到你 fork 的分支
```

### 步骤 5：发 Pull Request

1. 打开 `https://github.com/原作者/some-repo`
2. GitHub 通常会提示 "A pull request existed for `sainttelant/some-repo`..."，点 **Compare & pull request**
3. 方向是 `sainttelant/some-repo:my-feature` → `原作者/some-repo:主分支`
4. 填写说明，点 **Open pull request**

---

## 2. 备选流程：已经 Clone 了原仓库，现在想 Fork

如果你**已经** `git clone` 了原作者的仓库（remote 指向原仓库），想改成推自己的 fork：

### 步骤 1：网页上 Fork 到 `sainttelant`

（同「步骤 1」，得到 `https://github.com/sainttelant/some-repo`）

### 步骤 2：调整 remote

```bash
# 把原仓库改名为 upstream（保留，用于同步）
git remote rename origin upstream

# 把 origin 指向你自己的 fork（用个人别名！）
git remote add origin git@github-personal:sainttelant/some-repo.git

git remote -v
```

### 步骤 3：推送

```bash
git push -u origin main          # 首次推送，建立跟踪关系
# 之后正常：
git push origin main
```

---

## 3. 同步上游更新（保持 fork 最新）

原作者仓库更新了，你想把更新同步到自己的 fork：

```bash
git fetch upstream
git checkout main
git merge upstream/main          # 或 git rebase upstream/main
git push origin main             # 把更新推到你自己的 fork
```

> 如果 fork 落后太多，也可以直接在 GitHub 网页点
> `Sync fork → Update branch`，更省事。

---

## 4. 常见问题排查

### Q1：push 时报 `Permission to ... denied to wilson-xue_magna`
**原因**：remote 用了 `git@github.com:` 前缀，走了公司 key。
**解决**：把 remote 改成个人别名：
```bash
git remote set-url origin git@github-personal:sainttelant/some-repo.git
```

### Q2：push 时报 `Could not resolve hostname github.com`
**原因**：瞬时 DNS 抖动，不是 key 问题。
**解决**：稍等重试即可；持续出现则检查网络 / DNS。

### Q3：`ssh -T git@github-personal` 报 `banner exchange timed out`
**原因**：网络偶发超时（本机网络偶有丢包）。
**解决**：重试即可，通常不影响实际 `git push`。

### Q4：怎么确认当前 remote 用的是哪个账号？
```bash
git remote -v
# 看前缀：github-personal = 个人账号；github.com = 公司账号
```

---

## 附录：本机双账号配置（已配置好）

`~/.ssh/config`：

```sshconfig
# ===== 公司账号（默认，用于公司仓库）=====
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes

# ===== 个人账号 sainttelant（用于个人仓库 / fork）=====
Host github-personal
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_sainttelant
    IdentitiesOnly yes
```

对应的 key：

| 文件 | 账号 |
|------|------|
| `~/.ssh/id_ed25519` | 公司 `wilson-xue_magna` |
| `~/.ssh/id_ed25519_sainttelant` | 个人 `sainttelant` |

> 两把公钥需分别添加到对应 GitHub 账号的
> `Settings → SSH and GPG keys`。
