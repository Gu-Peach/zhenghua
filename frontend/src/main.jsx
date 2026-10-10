import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Bot,
  Boxes,
  FileJson,
  FileSpreadsheet,
  Files,
  FolderOpen,
  Loader2,
  MessageSquare,
  RefreshCw,
  Route,
  Send,
  Trash2,
  UploadCloud,
} from 'lucide-react'
import { deleteJob, getJob, listJobs, processPdf } from './api'
import { WIRE_COLUMNS } from './constants'
import { formatDate, publicAssetUrl } from './utils'
import './styles.css'

function App() {
  const [route, setRoute] = useState(location.hash || '#/process')
  const [jobs, setJobs] = useState([])
  const [selectedJob, setSelectedJob] = useState(null)
  const [activeJob, setActiveJob] = useState(null)
  const [file, setFile] = useState(null)
  const [processing, setProcessing] = useState(false)
  const [statusText, setStatusText] = useState('等待上传 PDF')
  const [messages, setMessages] = useState([
    { role: 'ai', text: '上传 PDF 后，我会先拆分页面并归类，再提取线表并存入 public 管理库。' },
  ])

  useEffect(() => {
    const onHashChange = () => setRoute(location.hash || '#/process')
    window.addEventListener('hashchange', onHashChange)
    refreshJobs()
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    if (!activeJob?.job_id || activeJob.status !== 'processing') {
      if (activeJob?.job_id) setProcessing(false)
      return undefined
    }

    let stopped = false
    async function pollJob() {
      try {
        const data = await getJob(activeJob.job_id)
        if (stopped) return
        setActiveJob(data)
        setSelectedJob(data)
        setStatusText(data.status_message || statusLabel(data))
        await refreshJobs()
        if (data.status !== 'processing') {
          setProcessing(false)
          setMessages((items) => [...items, { role: 'ai', text: `${data.name} ${statusLabel(data)}。` }])
        }
      } catch (error) {
        if (!stopped) {
          setStatusText(`轮询失败：${error.message}`)
        }
      }
    }

    const timer = window.setInterval(pollJob, 2500)
    pollJob()
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [activeJob?.job_id, activeJob?.status])

  const visibleJob = route === '#/process' ? activeJob || selectedJob : selectedJob

  async function refreshJobs() {
    const data = await listJobs()
    setJobs(data)
  }

  async function openJob(jobId, navigate = true) {
    const data = await getJob(jobId)
    setSelectedJob(data)
    if (navigate) location.hash = '#/library'
  }

  async function handleProcess() {
    if (!file || processing) return
    setProcessing(true)
    setStatusText('正在处理 PDF...')
    setMessages((items) => [
      ...items,
      { role: 'user', text: `处理 ${file.name}` },
      { role: 'ai', text: '开始执行：PDF 拆页、页面归类、按组提取、写入 public 管理库。' },
    ])
    try {
      const data = await processPdf(file)
      setActiveJob(data.job)
      setSelectedJob(data.job)
      setStatusText(data.job.status_message || statusLabel(data.job))
      setProcessing(data.job.status === 'processing')
      setMessages((items) => [...items, { role: 'ai', text: `${data.job.name} 已创建任务，后台会持续处理并刷新结果。` }])
      await refreshJobs()
    } catch (error) {
      setStatusText('处理失败')
      setMessages((items) => [...items, { role: 'ai', text: `处理失败：${error.message}` }])
      setProcessing(false)
    }
  }

  async function handleDelete() {
    if (!selectedJob) return
    if (!confirm(`删除 ${selectedJob.name}？`)) return
    await deleteJob(selectedJob.job_id)
    setSelectedJob(null)
    setActiveJob((job) => (job?.job_id === selectedJob.job_id ? null : job))
    await refreshJobs()
  }

  return (
    <div className="app">
      <Header route={route} />
      <main className="shell">
        <Sidebar jobs={jobs} selectedId={selectedJob?.job_id || activeJob?.job_id} onRefresh={refreshJobs} onOpenJob={openJob} />
        <section className="workspace">
          {route === '#/library' ? (
            <LibraryPage job={selectedJob} onDelete={handleDelete} />
          ) : (
            <ProcessPage
              file={file}
              job={visibleJob}
              processing={processing}
              statusText={statusText}
              onFile={setFile}
              onProcess={handleProcess}
            />
          )}
        </section>
        <ChatPanel messages={messages} setMessages={setMessages} job={visibleJob} />
      </main>
    </div>
  )
}

function Header({ route }) {
  return (
    <header className="header">
      <div className="brand-mark">线</div>
      <div className="brand-copy">
        <strong>线表智能提取系统</strong>
        <span>PDF 图纸识别与结果管理</span>
      </div>
      <nav className="tabs" aria-label="页面路由">
        <button className={route === '#/process' ? 'active' : ''} onClick={() => (location.hash = '#/process')}>
          <Route size={16} />处理页
        </button>
        <button className={route === '#/library' ? 'active' : ''} onClick={() => (location.hash = '#/library')}>
          <FolderOpen size={16} />管理页
        </button>
      </nav>
      <div className="profile">
        <span>AI</span>
        <strong>操作员</strong>
      </div>
    </header>
  )
}

function Sidebar({ jobs, selectedId, onRefresh, onOpenJob }) {
  return (
    <aside className="sidebar">
      <div className="panel-title">
        <span>文件列表</span>
        <button className="icon-button" onClick={onRefresh} title="刷新文件列表">
          <RefreshCw size={16} />
        </button>
      </div>
      <div className="job-list">
        {jobs.length === 0 ? <Empty text="暂无处理记录" /> : null}
        {jobs.map((job) => (
          <button key={job.job_id} className={`job-item ${selectedId === job.job_id ? 'selected' : ''}`} onClick={() => onOpenJob(job.job_id)}>
            <Files size={18} />
            <span className="job-content">
              <strong>{job.name}</strong>
              <small>{job.source_filename}</small>
              <em>{job.group_count} 个线表 · {job.record_count} 条记录</em>
            </span>
          </button>
        ))}
      </div>
    </aside>
  )
}

function ProcessPage({ file, job, processing, statusText, onFile, onProcess }) {
  return (
    <>
      <PageHead title="PDF 线表提取" subtitle="上传 PDF 后自动拆页、归类，并按线表批次调用视觉模型。">
        <span className={`status-pill ${processing ? 'working' : ''}`}>{processing ? <Loader2 size={14} className="spin" /> : null}{statusText}</span>
      </PageHead>
      <UploadArea file={file} disabled={processing} onFile={onFile} onProcess={onProcess} />
      {job ? <JobDetail job={job} /> : <FlowStrip />}
    </>
  )
}

function LibraryPage({ job, onDelete }) {
  return (
    <>
      <PageHead title="管理库" subtitle="public/library 下按文件夹保存原始 PDF、拆页图片、线表 JSON 和 XLSX。">
        {job ? <button className="danger-button" onClick={onDelete}><Trash2 size={16} />删除文件夹</button> : null}
      </PageHead>
      {job ? <JobDetail job={job} /> : <Empty text="从左侧选择一个处理结果" large />}
    </>
  )
}

function PageHead({ title, subtitle, children }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {children}
    </div>
  )
}

function UploadArea({ file, disabled, onFile, onProcess }) {
  const [dragging, setDragging] = useState(false)

  function selectFile(event) {
    onFile(event.target.files?.[0] || null)
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    const dropped = [...event.dataTransfer.files].find((item) => item.type === 'application/pdf' || item.name.endsWith('.pdf'))
    if (dropped) onFile(dropped)
  }

  return (
    <section
      className={`upload-area ${dragging ? 'dragging' : ''}`}
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <input id="pdf-input" type="file" accept="application/pdf" hidden onChange={selectFile} />
      <div className="pdf-badge">PDF</div>
      <strong>{file ? file.name : '拖拽或选择 PDF 文件'}</strong>
      <span>处理结果会写入 frontend/public/library，用于前端管理页读取。</span>
      <div className="button-row">
        <button className="primary-button" onClick={() => document.getElementById('pdf-input').click()}>
          <UploadCloud size={17} />选择文件
        </button>
        <button className="secondary-button" disabled={!file || disabled} onClick={onProcess}>
          {disabled ? <Loader2 size={17} className="spin" /> : <Boxes size={17} />}开始处理
        </button>
      </div>
    </section>
  )
}

function FlowStrip() {
  const steps = ['PDF 拆页', '页面归类', '线表提取', '写入 public']
  return (
    <div className="flow-strip">
      {steps.map((step, index) => (
        <div key={step}><b>{index + 1}</b><span>{step}</span></div>
      ))}
    </div>
  )
}

function JobDetail({ job }) {
  const groups = job.groups || []
  return (
    <div className="result-layout">
      <section className="summary-card">
        <div>
          <span className="eyebrow">{job.status}</span>
          <h2>{job.name}</h2>
          <p>{job.source_filename} · {formatDate(job.created_at)}</p>
        </div>
        <div className="metrics">
          <Metric value={job.page_count} label="页面" />
          <Metric value={job.group_count} label="线表" />
          <Metric value={job.record_count} label="记录" />
        </div>
        {job.source_url ? <a className="file-link" href={publicAssetUrl(job.source_url)} target="_blank" rel="noreferrer">打开原始 PDF</a> : null}
      </section>
      <section className="group-grid">
        {groups.map((group) => <GroupCard key={group.group_id} group={group} />)}
      </section>
      <AgentDiagnostics job={job} />
    </div>
  )
}

function AgentDiagnostics({ job }) {
  const diagnostics = job.manifest?.grouping_raw || {}
  const batches = diagnostics.extraction_batches || []
  const warnings = diagnostics.validation_warnings || []
  const indexPages = diagnostics.drawing_index?.pages?.length || 0
  if (!batches.length && !indexPages && !warnings.length) return null
  return (
    <section className="diagnostic-strip">
      <div><strong>Agent 诊断</strong><span>索引页 {indexPages}</span><span>提取批次 {batches.length}</span><span>复核提示 {warnings.length}</span></div>
      <a href={`/library/${job.job_id}/agent/drawing_index.json`} target="_blank" rel="noreferrer"><FileJson size={15} />索引 JSON</a>
    </section>
  )
}

function Metric({ value, label }) {
  return <div className="metric"><b>{value}</b><span>{label}</span></div>
}

function GroupCard({ group }) {
  return (
    <article className="group-card">
      <div className="group-head">
        <div>
          <h3>{group.title}</h3>
          <span>页面 {group.pages?.join(', ')} · {group.record_count} 条</span>
        </div>
        <div className="group-actions">
          {group.json_url ? <a href={publicAssetUrl(group.json_url)} target="_blank" rel="noreferrer"><FileJson size={16} />JSON</a> : null}
          {group.xlsx_url ? <a href={publicAssetUrl(group.xlsx_url)} target="_blank" rel="noreferrer"><FileSpreadsheet size={16} />XLSX</a> : null}
          {group.import_xlsx_url ? <a href={publicAssetUrl(group.import_xlsx_url)} target="_blank" rel="noreferrer"><FileSpreadsheet size={16} />导入 XLSX</a> : null}
          {group.import_xls_url ? <a href={publicAssetUrl(group.import_xls_url)} target="_blank" rel="noreferrer"><FileSpreadsheet size={16} />导入 XLS</a> : null}
        </div>
      </div>
      {group.reason ? <p className="reason">{group.reason}</p> : null}
      {group.error ? <div className="error-box">{group.error}</div> : <WireTable records={group.records || []} />}
    </article>
  )
}

function WireTable({ records }) {
  if (!records.length) return <Empty text="暂无线表记录" />
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{WIRE_COLUMNS.map(([, label]) => <th key={label}>{label}</th>)}</tr>
        </thead>
        <tbody>
          {records.map((record, index) => (
            <tr key={`${record.line_number || 'row'}-${index}`}>
              {WIRE_COLUMNS.map(([key]) => <td key={key}>{record[key] ?? ''}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ChatPanel({ messages, setMessages, job }) {
  const [text, setText] = useState('')
  const hint = useMemo(() => {
    if (!job) return '当前还没有选中结果。请先上传 PDF 或从左侧选择历史文件夹。'
    return `当前选中 ${job.name}，包含 ${job.group_count} 个线表、${job.record_count} 条记录。`
  }, [job])

  function submit(event) {
    event.preventDefault()
    const value = text.trim()
    if (!value) return
    setText('')
    setMessages((items) => [...items, { role: 'user', text: value }, { role: 'ai', text: hint }])
  }

  return (
    <aside className="chat-panel">
      <div className="panel-title"><span>AI 对话框</span><MessageSquare size={17} /></div>
      <div className="chat-feed">
        {messages.map((message, index) => (
          <div key={index} className={`chat-message ${message.role}`}>
            {message.role === 'ai' ? <Bot size={15} /> : null}
            <span>{message.text}</span>
          </div>
        ))}
      </div>
      <form className="chat-input" onSubmit={submit}>
        <input value={text} onChange={(event) => setText(event.target.value)} placeholder="询问本次提取结果..." />
        <button type="submit"><Send size={16} /></button>
      </form>
    </aside>
  )
}

function Empty({ text, large = false }) {
  return <div className={`empty ${large ? 'large' : ''}`}>{text}</div>
}

function statusLabel(job) {
  if (!job) return '等待处理'
  if (job.status === 'processing') return job.status_message || '处理中'
  if (job.status === 'success') return `处理完成：${job.group_count} 个线表，${job.record_count} 条记录`
  if (job.status === 'partial') return `部分完成：${job.record_count} 条记录`
  if (job.status === 'failed') return '处理失败'
  return job.status || '未知状态'
}

createRoot(document.getElementById('app')).render(<App />)
