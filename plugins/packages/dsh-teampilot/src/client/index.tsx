import { useEffect, useId, useRef, useState, useSyncExternalStore } from 'react'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type {} from '@deepseek-ai/dsh-client-ui-layout/client'
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-api-session-controller/client'
import type {} from '@deepseek-ai/dsh-client-ui-workspace/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-right/client'
import { Button, Input, SegmentedTabs } from '@deepseek-ai/dsh-client-ui-primitives'
import { BriefcaseBusiness, RefreshCw, LogOut, Check, Ban, MessageSquare, ExternalLink } from 'lucide-react'
import type { RemoteResult } from '@deepseek-ai/dsh-typert-protocol'
import type { ConnectionStatus } from '../shared/types.js'
import contribution from '../../lib/typert.remote-client.js'
import { startConversation } from './session.js'
import { approvalStatus, buildReviewRows, commitInstruction, panelStorageKey, projectOptions, readPanelState, savePanelState } from './review.js'
export { approvalStatus, buildReviewRows, commitInstruction, panelStorageKey, projectOptions, readPanelState, savePanelState } from './review.js'
import css from './style.css'

export { startConversation } from './session.js'
export const inject = ['slots', 'remote', 'sessions', 'uiWorkspace', 'sidebarRight', 'sidebarRightTabs']

function unwrap<T>(result: RemoteResult<T>): T {
  if (!result.ok) throw new Error(result.error.message)
  return result.value
}
interface Project { id: string; name: string }
interface Draft { id: string; state: string; payload_hash: string; expires_at: string; approval_expires_at?: string | null; approval_available?: boolean;
  payload: { kind: string; name?: string; project_id?: string; [key: string]: unknown };
  preview?: { items: { title: string; before: unknown; after: unknown }[]; weight_policy?: string; display_names?: Record<string, string>; project_name?: string } }
const kindLabels: Record<string, string> = { project_plan: '项目计划', task_create: '新增任务', task_update: '任务修改', progress: '进度更新' }
const stateLabels: Record<string, string> = { pending: '待审阅', approved: '已批准', committed: '已提交', cancelled: '已取消' }

export async function apply(ctx: Context): Promise<void> {
  await ctx.remote.$mount(contribution)
  ctx.effect(() => {
    const style = document.createElement('style')
    style.textContent = css
    document.head.append(style)
    return () => style.remove()
  })
  ctx.inject(['slots', 'remote.teampilot', 'remote.agentPresets', 'sessions', 'uiWorkspace', 'sidebarRight', 'sidebarRightTabs'], mountPanel)
}

function mountPanel(ctx: Context): void {
  let grouped = false
  const listeners = new Set<() => void>()
  ctx.effect(() => {
    // Native DSH's pluginNavigation opens manager details; it is not the shared
    // business launcher. Observe that launcher's actual public slot registration.
    const sync = () => {
      const next = ctx.slots.entriesOfSlot('sidebar.footer.action').some(entry => entry.options.id === 'plugin-navigation')
      if (next !== grouped) { grouped = next; listeners.forEach(listener => listener()) }
    }
    const dispose = ctx.slots.subscribe('sidebar.footer.action', sync)
    sync()
    return dispose
  })
  function Launcher({ wide = false }: { wide?: boolean }) {
    const managed = useSyncExternalStore(listener => { listeners.add(listener); return () => { listeners.delete(listener) } }, () => grouped)
    if (managed) return null
    return <Button size="sm" title="TeamPilot" aria-label="TeamPilot" onClick={() => ctx.sidebarRight.openTab('teampilot')} icon={<BriefcaseBusiness size={18} />}>{wide ? 'TeamPilot' : null}</Button>
  }
  function Panel({ sessionId }: { sessionId: string }) {
    const paneId = useId()
    const [status, setStatus] = useState<ConnectionStatus | null>(null)
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [projects, setProjects] = useState<Project[]>([])
    const [projectId, setProjectId] = useState('')
    const [projectName, setProjectName] = useState('')
    const [projectSearch, setProjectSearch] = useState('')
    const [projectPage, setProjectPage] = useState(1)
    const [projectTotal, setProjectTotal] = useState(0)
    const [drafts, setDrafts] = useState<Draft[]>([])
    const [selected, setSelected] = useState('')
    const [reviewed, setReviewed] = useState(false)
    const [prompt, setPrompt] = useState('')
    const [view, setView] = useState<'query' | 'drafts'>('query')
    const [lastSessionId, setLastSessionId] = useState('')
    const [storageKey, setStorageKey] = useState('')
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    const [projectError, setProjectError] = useState('')
    const [draftError, setDraftError] = useState('')
    const [projectUpdated, setProjectUpdated] = useState('')
    const [draftUpdated, setDraftUpdated] = useState('')
    const [copyNotice, setCopyNotice] = useState('')
    const [clock, setClock] = useState(Date.now())
    const controller = useRef(new AbortController())
    const busyRef = useRef(false)
    const identity = useRef('')
    const draft = drafts.find(item => item.id === selected)
    const approval = draft ? approvalStatus(draft, clock) : null
    const options = projectOptions(projects, projectId ? { id: projectId, name: projectName || projectId } : null, projectSearch)
    const pendingCount = drafts.filter(item => ['pending', 'approved'].includes(item.state) && Date.parse(item.expires_at) > clock).length
    const storage = () => { try { return window.localStorage } catch { return undefined } }
    const formatTime = (value: string) => value ? new Date(value).toLocaleString() : '尚未读取'
    function clearAccountData() {
      identity.current = ''; setStorageKey(''); setProjects([]); setDrafts([]); setProjectId(''); setProjectName(''); setSelected(''); setPrompt(''); setLastSessionId('')
      setProjectTotal(0); setProjectPage(1); setProjectUpdated(''); setDraftUpdated(''); setProjectError(''); setDraftError(''); setCopyNotice(''); setReviewed(false); setView('query')
    }

    async function run(operation: (signal: AbortSignal) => Promise<void>) {
      if (busyRef.current) return
      busyRef.current = true; setBusy(true); setError('')
      try { await operation(controller.current.signal) }
      catch (reason) { if (!controller.current.signal.aborted) setError(reason instanceof Error ? reason.message : '请求失败，请重试') }
      finally { busyRef.current = false; if (!controller.current.signal.aborted) setBusy(false) }
    }
    async function reload(signal: AbortSignal, targetPage = projectPage) {
      const current = unwrap(await ctx.remote.teampilot.status(signal))
      signal.throwIfAborted()
      setStatus(current)
      if (!current.connected) {
        clearAccountData()
        return
      }
      const key = panelStorageKey(current.baseUrl, current.username)
      if (identity.current !== key) {
        // Previous data is safe to retain only for the same account. A failed
        // first read for the new account must never display another user's list.
        setProjects([]); setDrafts([]); setProjectTotal(0); setProjectPage(1)
        setProjectUpdated(''); setDraftUpdated(''); setProjectError(''); setDraftError(''); setCopyNotice('')
        const saved = readPanelState(storage(), key)
        identity.current = key; setStorageKey(key); setProjectId(saved.projectId); setProjectName(saved.projectName)
        setPrompt(saved.prompt); setView(saved.view); setSelected(saved.selected); setLastSessionId(saved.sessionId)
        setReviewed(false); setProjectSearch(''); targetPage = 1
      }
      const [p, d] = await Promise.allSettled([
        ctx.remote.teampilot.read({ resource: 'projects', page: targetPage }, signal).then(result => JSON.parse(unwrap(result).json)),
        ctx.remote.teampilot.read({ resource: 'drafts', page: 1 }, signal).then(result => JSON.parse(unwrap(result).json)),
      ])
      signal.throwIfAborted()
      // Another native pane can switch the single Host account between these
      // independent reads. Confirm the same identity before adopting either list.
      const latest = unwrap(await ctx.remote.teampilot.status(signal))
      signal.throwIfAborted()
      if (!latest.connected || panelStorageKey(latest.baseUrl, latest.username) !== key) {
        clearAccountData(); setStatus(latest)
        throw new Error('读取期间账号发生变化，已清空旧内容。请重新连接以读取当前账号的数据。')
      }
      if (p.status === 'fulfilled') {
        setProjects(p.value.items); setProjectTotal(p.value.total); setProjectPage(targetPage); setProjectError('')
        setProjectUpdated(p.value.queried_at || new Date().toISOString())
      } else setProjectError('项目读取失败；已保留上次列表和已选范围。')
      if (d.status === 'fulfilled') {
        setDrafts(d.value.items); setDraftError(''); setDraftUpdated(d.value.queried_at || new Date().toISOString())
      } else setDraftError('草稿读取失败；已保留上次审阅内容，请重试。')
    }
    useEffect(() => {
      controller.current = new AbortController()
      void run(signal => reload(signal))
      const timer = setInterval(() => setClock(Date.now()), 10000)
      return () => { controller.current.abort(); clearInterval(timer) }
    }, [])
    useEffect(() => {
      if (storageKey && identity.current === storageKey) savePanelState(storage(), storageKey, {
        projectId, projectName, prompt, view, selected, sessionId: lastSessionId,
      })
    }, [storageKey, projectId, projectName, prompt, view, selected, lastSessionId])
    useEffect(() => { setReviewed(false); setCopyNotice('') }, [selected, draft?.payload_hash])
    function selectView(next: 'query' | 'drafts') {
      setView(next)
      if (next === 'drafts') void run(signal => reload(signal))
    }
    async function startSession(signal: AbortSignal) {
      await startConversation(ctx, { projectId, prompt, onAdmitted: id => {
        savePanelState(storage(), identity.current, { projectId, projectName, prompt: '', view, selected, sessionId: id })
        setLastSessionId(id); setPrompt('')
      } }, signal)
    }
    async function copyInstruction() {
      if (!draft) return
      try { await navigator.clipboard.writeText(commitInstruction(draft.id)); setCopyNotice('已复制。请回到 DSH 对话粘贴，再确认原生审批。') }
      catch { setCopyNotice('无法访问剪贴板，请手动复制下方提交请求。') }
    }
    async function openLastSession(signal: AbortSignal) {
      await ctx.sessions.refresh()
      signal.throwIfAborted()
      const id = ctx.sessions.list.getSnapshot().ids.find(item => item === lastSessionId)
      if (!id) throw new Error('最近分析对话已不在此 DSH 中，请在宿主会话列表查找，或将提交请求粘贴到合适的对话。')
      ctx.uiWorkspace.openSession(id)
    }
    return <section className="tp-panel" aria-label="TeamPilot" aria-busy={busy} data-session-id={sessionId}>
      <header><div><h2>TeamPilot</h2><span>{status?.connected ? status.username : '项目管理'}</span></div>
        <div className="tp-tools"><Button size="sm" title="刷新" aria-label="刷新" disabled={busy} onClick={() => void run(signal => reload(signal))}><RefreshCw size={16} /></Button>
          {status?.connected && <Button size="sm" title="退出账号" aria-label="退出账号" disabled={busy} onClick={() => void run(async signal => { await ctx.remote.teampilot.logout(signal).then(unwrap); await reload(signal) })}><LogOut size={16} /></Button>}
          {status && <a href={status.webUrl} target="_blank" rel="noopener noreferrer" title="打开管理网页" aria-label="打开管理网页"><ExternalLink size={18} /></a>}</div>
      </header>
      {error && <div className="tp-error" role="alert"><p>{error}</p><Button size="sm" disabled={busy} onClick={() => void run(signal => reload(signal))}>重新连接</Button></div>}
      {!status ? <p className="tp-muted" role="status">{busy ? '正在连接…' : '连接未完成，请重试。'}</p> : !status.connected ? <form className="tp-login" onSubmit={event => { event.preventDefault(); const secret = password; setPassword(''); void run(async signal => { unwrap(await ctx.remote.teampilot.login({ username, password: secret }, signal)); await reload(signal) }) }}>
        <label>用户名<Input required autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} /></label>
        <label>密码<Input required type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></label>
        <Button type="submit" variant="primary" disabled={busy}>{busy ? '正在登录…' : '登录'}</Button></form> : <>
        <SegmentedTabs label="TeamPilot 功能" value={view} onChange={selectView} items={[{ value: 'query', label: '查询分析', id: `${paneId}-query-tab`, panelId: `${paneId}-query` }, { value: 'drafts', label: `草稿审阅${pendingCount ? ` (${pendingCount})` : ''}`, id: `${paneId}-drafts-tab`, panelId: `${paneId}-drafts` }]} />
        {view === 'query' && <form id={`${paneId}-query`} role="tabpanel" aria-labelledby={`${paneId}-query-tab`} className="tp-compose" onSubmit={event => { event.preventDefault(); void run(startSession) }}>
          {projectError && <div className="tp-error" role="alert">{projectError}<Button size="sm" disabled={busy} onClick={() => void run(signal => reload(signal))}>重试</Button></div>}
          <label>查找项目<Input value={projectSearch} placeholder="筛选当前页项目名称" onChange={event => setProjectSearch(event.target.value)} /></label>
          <label>查询范围<select aria-label="项目" value={projectId} disabled={busy} onChange={event => { const id = event.target.value; setProjectId(id); setProjectName(options.find(item => item.id === id)?.name || '') }}><option value="">全部有权访问的项目</option>{options.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
          <p className="tp-muted">已选范围：{projectId ? projectName || projectId : '全部有权访问的未归档项目'}。{projectTotal > 50 ? '已选项目跨页保留；名称筛选只匹配当前页。' : ''}</p>
          {projectTotal > 50 && <div className="tp-pagination"><Button disabled={busy || projectPage === 1} onClick={() => void run(signal => reload(signal, projectPage - 1))}>上一页</Button><span>{projectPage} / {Math.ceil(projectTotal / 50)} · {projectTotal} 个项目</span><Button disabled={busy || projectPage * 50 >= projectTotal} onClick={() => void run(signal => reload(signal, projectPage + 1))}>下一页</Button></div>}
          <p className="tp-muted">项目读取：{formatTime(projectUpdated)}</p>
          <label>需求<textarea placeholder="例如：汇总本周项目进展，列出延期任务及依据" value={prompt} rows={5} maxLength={20000} onChange={event => setPrompt(event.target.value)} /></label>
          <Button type="submit" variant="primary" disabled={busy || !prompt.trim()}><MessageSquare size={16} />{busy ? '正在提交…' : '开始分析'}</Button>
          <p className="tp-muted">未提交需求按账号保存在此浏览器；提交成功后清空。结果将在 DSH 对话中展示，可继续追问。修改建议需另行审阅确认。</p>
          {lastSessionId && <Button disabled={busy} onClick={() => void run(openLastSession)}>打开最近分析对话</Button>}
        </form>}
        {view === 'drafts' && <section id={`${paneId}-drafts`} role="tabpanel" aria-labelledby={`${paneId}-drafts-tab`} className="tp-drafts">
          <div className="tp-status-line"><p className="tp-muted">草稿读取：{formatTime(draftUpdated)}{busy ? ' · 正在刷新…' : ''}</p><Button size="sm" disabled={busy} onClick={() => void run(signal => reload(signal))}>刷新草稿</Button></div>
          {draftError && <div className="tp-error" role="alert">{draftError}<Button size="sm" disabled={busy} onClick={() => void run(signal => reload(signal))}>重试</Button></div>}
          <div className="tp-review-grid"><nav aria-label="草稿列表">{drafts.length ? drafts.map(item => <Button className={selected === item.id ? 'selected' : ''} aria-pressed={selected === item.id} onClick={() => setSelected(item.id)} key={item.id}><strong>{item.payload.name || kindLabels[item.payload.kind] || item.payload.kind}</strong><span>{approvalStatus(item, clock).label} · {item.id.slice(0, 8)}</span></Button>) : !draftError && <p className="tp-muted">{busy ? '正在读取草稿…' : '暂无草稿。请先在 DSH 对话中明确提出修改需求，再到这里审阅。'}</p>}</nav>
            <div className="tp-review">{draft && approval ? <>
              <p className={approval.ready ? 'tp-notice' : 'tp-warning'} role="status">{approval.label}</p>
              <dl><dt>类型</dt><dd>{kindLabels[draft.payload.kind] || draft.payload.kind}</dd><dt>项目</dt><dd>{draft.payload.name || draft.preview?.project_name || projects.find(item => item.id === draft.payload.project_id)?.name || draft.payload.project_id}</dd><dt>草稿到期</dt><dd>{formatTime(draft.expires_at)}（生成后 1 小时）</dd>{draft.approval_expires_at && <><dt>批准到期</dt><dd>{formatTime(draft.approval_expires_at)}（批准后最多 5 分钟）</dd></>}</dl>
              {draft.preview?.weight_policy && <p className="tp-warning">新增子任务会均分所有同级子任务权重，已完成的父级和祖先会重新打开。</p>}
              {draft.preview?.items.map((item, index) => <article key={index}><h4>{item.title}</h4><div className="tp-table-scroll"><table className="tp-diff-table"><caption>{item.title}：修改前后对照</caption><thead><tr><th scope="col">字段</th><th scope="col">修改前</th><th scope="col">修改后</th></tr></thead><tbody>{buildReviewRows(item.before, item.after, draft.preview?.display_names).map(row => <tr key={row.key} className={row.changed ? 'tp-changed' : ''}><th scope="row">{row.label}</th><td>{row.before}</td><td>{row.after}{row.changed && <span className="tp-change-label">变更</span>}</td></tr>)}</tbody></table></div></article>)}
              <details><summary>完整草稿内容（JSON）</summary><pre>{JSON.stringify(draft.payload, null, 2)}</pre></details>
              {approval.mayApprove && <footer><label className="tp-confirm"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />我已核对上述修改前后内容</label><div className="tp-tools"><Button disabled={busy} onClick={() => void run(async signal => { unwrap(await ctx.remote.teampilot.cancel({ draftId: draft.id }, signal)); await reload(signal) })}><Ban size={16} />取消草稿</Button><Button variant="primary" disabled={busy || !reviewed || Boolean(draftError)} onClick={() => void run(async signal => { unwrap(await ctx.remote.teampilot.approve({ draftId: draft.id, payloadHash: draft.payload_hash }, signal)); setReviewed(false); await reload(signal) })}><Check size={16} />{draft.state === 'approved' ? '重新审阅批准' : '批准此草稿'}</Button></div></footer>}
              {approval.ready && <div className="tp-next-step"><h4>下一步：在 DSH 对话请求提交</h4><p>此次批准尚未修改业务数据。复制下方请求到 DSH 对话，再确认 DSH 原生审批；两步均通过后才会写入。</p><label>提交请求<textarea readOnly value={commitInstruction(draft.id)} rows={4} /></label><div className="tp-tools"><Button disabled={busy} onClick={() => void copyInstruction()}>复制提交请求</Button>{lastSessionId && <Button disabled={busy} onClick={() => void run(openLastSession)}>打开最近分析对话</Button>}<Button disabled={busy} onClick={() => void run(async signal => { unwrap(await ctx.remote.teampilot.cancel({ draftId: draft.id }, signal)); await reload(signal) })}>取消草稿</Button></div>{copyNotice && <p role="status">{copyNotice}</p>}</div>}
            </> : <p className="tp-muted">{selected ? '原选草稿不在当前列表中，请重新选择。' : '选择草稿查看修改前后内容。'}</p>}</div>
          </div>
        </section>}
      </>}
    </section>
  }

  ctx.slots.inject('sidebar.footer.action', () => ctx.slots.register({ name: 'sidebar.footer.action', id: 'teampilot', order: 350 }, Launcher))
  ctx.effect(() => ctx.sidebarRightTabs.register({ id: 'dsh-teampilot', kind: 'teampilot', priority: 'extension', title: () => 'TeamPilot', guide: [{ id: 'teampilot', order: 35, title: () => 'TeamPilot', description: () => '登录、查询项目与审阅建议', icon: BriefcaseBusiness }] }))
  ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({ name: 'sidebar.right.pane.tab', key: 'dsh-teampilot' }, Panel))
}
