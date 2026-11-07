## 做了什么

<!-- 一两句话。读者应该能在不打开 diff 的情况下知道这个 PR 解决了什么。 -->

## 为什么

<!-- 触发它的问题、讨论或工单。没有背景的改动，未来会被当成可以随手删掉的改动。 -->

## 怎么验的

<!-- 贴命令与结果，不要只写"已测试"。 -->

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 tools/check_docs.py
python3 tools/gen_catalog.py --check
python3 tools/check_hosts.py
python3 tools/check_nuclear_dev_agent.py
```

- [ ] 以上五条全绿
- [ ] 改了 `skills/*/SKILL.md` 的话，`catalog.json` 已重新生成，两份 `host-compatibility.md` 的字节数已同步
- [ ] 改了 `nuclear-dev-agent/` 的话，`pnpm typecheck && pnpm test` 通过，`FORK.md` 已记改动

## 有没有碰判定规则

- [ ] 没有碰 `nuclearlib.py` 的判定逻辑；或者：碰了，并在下面说明改了什么、为什么必须改、补了哪些用例

> 任何情况下都不得新增批准通道：不生成、不修改、不推断 `.nuclear-dev/approvals/*.json`，
> 不为了让门禁"看起来通过"而放宽规则。

## 没做什么

<!-- 明确写出来：被拒绝的方案及理由、留待后续的口子、已知限制。这比藏在脑子里有用。 -->
