import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Card,
  Divider,
  Empty,
  Form,
  Input,
  Layout,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { TableColumnsType } from 'antd'
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import type { ShotRead, ShotStatus } from '../../../services/generated'
import { ScriptProcessingService, StudioChaptersService, StudioShotsService } from '../../../services/generated'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { getChapterShotEditPath, getChapterStudioPath } from '../project/ProjectWorkbench/routes'

const { Header, Content } = Layout

function getErrorMessage(e: unknown) {
  if (!e) return '请求失败'
  if (typeof e === 'string') return e
  if (typeof e === 'object') {
    const maybeAny = e as any
    const detail = maybeAny?.body?.detail ?? maybeAny?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    const msg = maybeAny?.message
    if (typeof msg === 'string' && msg.trim()) return msg
  }
  return '请求失败'
}

function statusTag(status?: ShotStatus) {
  if (!status) return <span className="text-gray-400">—</span>
  const color =
    status === 'ready' ? 'success' : status === 'generating' ? 'processing' : 'default'
  return <Tag color={color}>{status}</Tag>
}

export function ChapterShotsPage() {
  const navigate = useNavigate()
  const { projectId, chapterId } = useParams<{ projectId: string; chapterId: string }>()
  const [loading, setLoading] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [shots, setShots] = useState<ShotRead[]>([])
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [searchText, setSearchText] = useState('')
  const [chapterTitle, setChapterTitle] = useState<string>('')
  const [chapterIndex, setChapterIndex] = useState<number | null>(null)
  const [chapterRawText, setChapterRawText] = useState<string>('')
  const [chapterCondensedText, setChapterCondensedText] = useState<string>('')
  const [loadingChapter, setLoadingChapter] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [batchDeleting, setBatchDeleting] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [createSubmitting, setCreateSubmitting] = useState(false)
  const [createForm] = Form.useForm<{ title: string; script_excerpt?: string }>()

  const refresh = async () => {
    if (!chapterId) return
    setLoading(true)
    try {
      const res = await StudioShotsService.listShotsApiV1StudioShotsGet({
        chapterId,
        page: 1,
        pageSize: 100,
        order: 'index',
        isDesc: false,
      })
      setShots(res.data?.items ?? [])
      setSelectedRowKeys([])
    } catch {
      message.error('加载分镜失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setSelectedRowKeys([])
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterId])

  useEffect(() => {
    if (!chapterId) return
    setLoadingChapter(true)
    StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId })
      .then((res) => {
        const c = res.data
        setChapterTitle(c?.title ?? '')
        setChapterIndex(typeof c?.index === 'number' ? c.index : null)
        setChapterRawText(c?.raw_text?.trim?.() ? c.raw_text.trim() : '')
        setChapterCondensedText(c?.condensed_text?.trim?.() ? c.condensed_text.trim() : '')
      })
      .catch(() => {
        message.error('章节加载失败')
      })
      .finally(() => {
        setLoadingChapter(false)
      })
  }, [chapterId])

  const filteredShots = useMemo(() => {
    const q = searchText.trim().toLowerCase()
    if (!q) return shots
    return shots.filter((s) => {
      const title = String(s.title ?? '').toLowerCase()
      const ex = String(s.script_excerpt ?? '').toLowerCase()
      const idx = String(s.index)
      return title.includes(q) || ex.includes(q) || idx.includes(q)
    })
  }, [shots, searchText])

  const selectedShotIds = useMemo(() => selectedRowKeys.map((k) => String(k)), [selectedRowKeys])

  const openCreate = useCallback(() => {
    createForm.resetFields()
    setCreateOpen(true)
  }, [createForm])

  const closeCreate = useCallback(() => {
    setCreateOpen(false)
    createForm.resetFields()
  }, [createForm])

  const submitCreate = useCallback(async () => {
    if (!chapterId) return
    try {
      const v = await createForm.validateFields()
      setCreateSubmitting(true)
      const nextIndex = shots.reduce((m, s) => Math.max(m, s.index), 0) + 1
      const res = await StudioShotsService.createShotApiV1StudioShotsPost({
        requestBody: {
          id: crypto.randomUUID(),
          chapter_id: chapterId,
          index: nextIndex,
          title: v.title.trim(),
          script_excerpt: v.script_excerpt?.trim() ? v.script_excerpt.trim() : '',
          status: 'pending',
        },
      })
      const created = res.data
      if (created) {
        setShots((prev) => [...prev, created].sort((a, b) => a.index - b.index))
        message.success('已创建分镜')
        closeCreate()
      }
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) return
      message.error('创建失败')
    } finally {
      setCreateSubmitting(false)
    }
  }, [chapterId, closeCreate, createForm, shots])

  const handleOneClickExtract = useCallback(async () => {
    if (!chapterId) return
    const scriptText = (chapterCondensedText || chapterRawText).trim()
    if (!scriptText) {
      message.error('章节没有可用文本（condensed/raw 为空）')
      return
    }
    setExtracting(true)
    try {
      await ScriptProcessingService.divideScriptApiV1ScriptProcessingDividePost({
        requestBody: {
          script_text: scriptText,
          write_to_db: true,
          chapter_id: chapterId,
        },
      })
      message.success('已提取分镜')
      await refresh()
    } catch (e: unknown) {
      message.error(getErrorMessage(e))
    } finally {
      setExtracting(false)
    }
  }, [chapterCondensedText, chapterId, chapterRawText])

  const handleDelete = useCallback(
    async (shotId: string) => {
      setDeletingId(shotId)
      try {
        await StudioShotsService.deleteShotApiV1StudioShotsShotIdDelete({ shotId })
        setShots((prev) => prev.filter((s) => s.id !== shotId))
        setSelectedRowKeys((prev) => prev.filter((k) => String(k) !== shotId))
        message.success('已删除')
      } catch {
        message.error('删除失败')
      } finally {
        setDeletingId(null)
      }
    },
    [],
  )

  const handleBatchDelete = useCallback(async () => {
    if (selectedShotIds.length === 0) return
    const ids = [...selectedShotIds]

    setBatchDeleting(true)
    let ok = 0
    let fail = 0
    try {
      for (const id of ids) {
        try {
          await StudioShotsService.deleteShotApiV1StudioShotsShotIdDelete({ shotId: id })
          ok += 1
          setShots((prev) => prev.filter((s) => s.id !== id))
          setSelectedRowKeys((prev) => prev.filter((k) => String(k) !== id))
        } catch {
          fail += 1
        }
      }
    } finally {
      setBatchDeleting(false)
    }

    if (ok > 0 && fail === 0) {
      message.success(`已删除 ${ok} 条`)
    } else if (ok > 0 && fail > 0) {
      message.warning(`已删除 ${ok} 条，失败 ${fail} 条`)
    } else if (ok === 0 && fail > 0) {
      message.error(`删除失败（共 ${fail} 条）`)
    }
  }, [selectedShotIds])

  const columns: TableColumnsType<ShotRead> = useMemo(
    () => [
      {
        title: '序号',
        dataIndex: 'index',
        key: 'index',
        width: 72,
        align: 'center',
      },
      {
        title: '标题',
        dataIndex: 'title',
        key: 'title',
        width: 200,
        ellipsis: { showTitle: false },
        render: (t: string) => {
          const text = t?.trim() ? t : '—'
          return (
            <Tooltip title={text}>
              <span>{text}</span>
            </Tooltip>
          )
        },
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 120,
        render: (_: unknown, r) => statusTag(r.status),
      },
      {
        title: '剧本摘录',
        dataIndex: 'script_excerpt',
        key: 'script_excerpt',
        width: 280,
        ellipsis: { showTitle: false },
        render: (v: string | undefined) => {
          const raw = v?.trim() ?? ''
          const display = raw || '—'
          return (
            <Tooltip title={raw ? raw : undefined} placement="topLeft">
              <span className="block max-w-full overflow-hidden text-ellipsis whitespace-nowrap">{display}</span>
            </Tooltip>
          )
        },
      },
      {
        title: '操作',
        key: 'actions',
        width: 148,
        fixed: 'right',
        render: (_: unknown, r) => (
          <Space size={0} wrap>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              disabled={extracting}
              loading={extracting}
              onClick={() =>
                projectId &&
                chapterId &&
                navigate(getChapterShotEditPath(projectId, chapterId, r.id))
              }
            >
              编辑
            </Button>
            <Popconfirm
              title="确定删除该分镜？"
              okText="删除"
              cancelText="取消"
              onConfirm={() => void handleDelete(r.id)}
              okButtonProps={{ loading: extracting || deletingId === r.id, disabled: extracting }}
              cancelButtonProps={{ disabled: extracting }}
            >
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
                loading={extracting || deletingId === r.id}
                disabled={extracting}
              >
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [chapterId, deletingId, extracting, handleDelete, navigate, projectId],
  )

  const tableEmpty =
    !loading && shots.length === 0 ? (
      <Empty description="暂无分镜" />
    ) : !loading && filteredShots.length === 0 ? (
      <Empty description="没有匹配的分镜" image={Empty.PRESENTED_IMAGE_SIMPLE} />
    ) : undefined

  if (!projectId || !chapterId) {
    return <Navigate to="/projects" replace />
  }

  return (
    <Layout style={{ height: '100%', minHeight: 0, background: '#eef2f7' }}>
      <Header
        style={{
          padding: '0 16px',
          background: '#fff',
          borderBottom: '1px solid #e2e8f0',
          boxShadow: '0 2px 4px rgba(0,0,0,0.04)',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <Link
          to={`/projects/${projectId}?tab=chapters`}
          className="text-gray-600 hover:text-blue-600 flex items-center gap-1"
        >
          <ArrowLeftOutlined /> 返回章节列表
        </Link>
        <Divider type="vertical" />

        <div className="min-w-0 flex-1 overflow-hidden">
          <Typography.Text
            strong
            className="truncate block"
            style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          >
            {chapterIndex !== null ? `第${chapterIndex}章 · ${chapterTitle || '未命名'}` : chapterTitle || '章节'}
          </Typography.Text>
          <Typography.Text
            type="secondary"
            className="text-xs truncate block"
            style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          >
            {loadingChapter ? '加载中…' : '分镜列表'}
          </Typography.Text>
        </div>

        {shots.length > 0 ? (
          <Button
            type="primary"
            icon={<VideoCameraOutlined />}
            onClick={() => navigate(getChapterStudioPath(projectId, chapterId))}
          >
            进入拍摄
          </Button>
        ) : null}
      </Header>

      <Content
        style={{
          padding: 16,
          minHeight: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Card
          title="分镜"
          style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
          bodyStyle={{
            flex: 1,
            minHeight: 0,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            padding: 16,
          }}
          extra={
            <Space wrap>
              {selectedRowKeys.length > 0 ? (
                <>
                  <span className="text-gray-500 text-sm">已选 {selectedRowKeys.length} 项</span>
                  <Popconfirm
                    title={`确定删除选中的 ${selectedRowKeys.length} 条分镜？`}
                    okText="删除"
                    cancelText="取消"
                    onConfirm={() => void handleBatchDelete()}
                    okButtonProps={{ danger: true, loading: batchDeleting, disabled: extracting || batchDeleting }}
                    cancelButtonProps={{ disabled: extracting || batchDeleting }}
                  >
                    <Button danger icon={<DeleteOutlined />} loading={batchDeleting} disabled={extracting || batchDeleting}>
                      批量删除
                    </Button>
                  </Popconfirm>
                </>
              ) : null}
              {shots.length === 0 ? (
                <Button type="primary" loading={extracting} disabled={extracting} onClick={() => void handleOneClickExtract()}>
                  一键提取
                </Button>
              ) : null}
              <Button icon={<PlusOutlined />} onClick={openCreate} loading={extracting} disabled={extracting}>
                创建分镜
              </Button>
              <Button
                icon={<ReloadOutlined />}
                loading={extracting || loading}
                disabled={extracting || batchDeleting}
                onClick={() => void refresh()}
              >
                刷新
              </Button>
            </Space>
          }
        >
          <div className="flex flex-col gap-3 flex-1 min-h-0">
            <Input.Search
              allowClear
              placeholder="搜索序号、标题或剧本摘录…"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
            />
            <div className="flex-1 min-h-0">
              <Table<ShotRead>
                rowKey="id"
                size="small"
                loading={loading}
                rowSelection={{
                  selectedRowKeys,
                  onChange: (keys) => setSelectedRowKeys(keys),
                  getCheckboxProps: () => ({
                    disabled: extracting || batchDeleting,
                  }),
                }}
                columns={columns}
                dataSource={filteredShots}
                pagination={{ pageSize: 20, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100] }}
                scroll={{ x: 'max-content', y: 'calc(100vh - 300px)' }}
                locale={{
                  emptyText: tableEmpty ?? <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />,
                }}
              />
            </div>
          </div>
        </Card>
      </Content>

      <Modal
        title="创建分镜"
        open={createOpen}
        onCancel={extracting ? undefined : closeCreate}
        onOk={() => void submitCreate()}
        confirmLoading={extracting || createSubmitting}
        okButtonProps={{ loading: extracting || createSubmitting, disabled: extracting }}
        cancelButtonProps={{ disabled: extracting }}
        closable={!extracting}
        maskClosable={!extracting}
        keyboard={!extracting}
        destroyOnClose
        width={520}
      >
        <Form form={createForm} layout="vertical" preserve={false}>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请填写标题' }]}>
            <Input placeholder="分镜标题" />
          </Form.Item>
          <Form.Item name="script_excerpt" label="剧本摘录">
            <Input.TextArea rows={8} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>

    </Layout>
  )
}
