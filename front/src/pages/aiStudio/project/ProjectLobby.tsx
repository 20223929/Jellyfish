import React, { useEffect, useMemo, useState } from 'react'
import {
  Card,
  Input,
  Button,
  Progress,
  Statistic,
  Row,
  Col,
  Modal,
  Form,
  Select,
  InputNumber,
  Switch,
  message,
  Space,
  Tag,
  Popconfirm,
} from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  EnterOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  BarsOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { projects as mockProjects, type Project } from '../../../mocks/data'
import { StudioProjectsService } from '../../../services/generated'
import type { ProjectRead, ProjectStyle } from '../../../services/generated'

type ViewMode = 'grid' | 'compact' | 'large'
type FilterTab = 'all' | 'inProgress' | 'completed' | 'mine' | 'recent'
type SortKey = 'updatedAt' | 'name' | 'createdAt' | 'chapters'

const ProjectLobby: React.FC = () => {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [filterTab, setFilterTab] = useState<FilterTab>('all')
  const [sortKey, setSortKey] = useState<SortKey>('updatedAt')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [multiSelectMode, setMultiSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingProject, setEditingProject] = useState<Project | null>(null)
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()

  const useMock = import.meta.env.VITE_USE_MOCK === 'true'

  const toUIProject = (p: ProjectRead): Project => {
    const stats = (p.stats ?? {}) as Record<string, unknown>
    const getNum = (key: string) => {
      const v = stats[key]
      return typeof v === 'number' && Number.isFinite(v) ? v : 0
    }

    const updatedAt =
      (typeof stats.updated_at === 'string' && stats.updated_at) ||
      (typeof stats.updatedAt === 'string' && stats.updatedAt) ||
      new Date().toISOString()

    return {
      id: p.id,
      name: p.name,
      description: p.description ?? '',
      style: (p.style as Project['style']) ?? '现实主义',
      seed: p.seed ?? 0,
      unifyStyle: p.unify_style ?? true,
      progress: p.progress ?? 0,
      stats: {
        chapters: getNum('chapters'),
        roles: getNum('roles'),
        scenes: getNum('scenes'),
        props: getNum('props'),
      },
      updatedAt,
    }
  }

  const newProjectId = () => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
    return `p_${Date.now()}_${Math.random().toString(16).slice(2)}`
  }

  const load = async () => {
    setLoading(true)
    try {
      if (useMock) {
        setProjects(mockProjects)
      } else {
        const res = await StudioProjectsService.listProjectsApiV1StudioProjectsGet({
          page: 1,
          pageSize: 10,
        })
        const items = res.data?.items ?? []
        setProjects(items.map(toUIProject))
      }
    } catch {
      setProjects(useMock ? mockProjects : [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const getProjectStatus = (p: Project): 'draft' | 'inProgress' | 'completed' => {
    if (p.progress >= 90) return 'completed'
    if (p.progress <= 5) return 'draft'
    return 'inProgress'
  }

  const filteredSorted = useMemo(() => {
    const list = Array.isArray(projects) ? projects : []
    const keyword = search.trim().toLowerCase()

    let next = list.filter((p) => {
      if (keyword) {
        const inText =
          p.name.toLowerCase().includes(keyword) ||
          p.description.toLowerCase().includes(keyword)
        if (!inText) return false
      }

      if (filterTab === 'all') return true
      if (filterTab === 'inProgress') return getProjectStatus(p) === 'inProgress'
      if (filterTab === 'completed') return getProjectStatus(p) === 'completed'
      if (filterTab === 'recent') return true
      if (filterTab === 'mine') {
        // 目前没有 owner 字段，暂时视为全部
        return true
      }
      return true
    })

    if (filterTab === 'recent') {
      next = [...next].sort((a, b) =>
        b.updatedAt.localeCompare(a.updatedAt)
      ).slice(0, 5)
    }

    next.sort((a, b) => {
      let av: string | number = ''
      let bv: string | number = ''
      if (sortKey === 'name') {
        av = a.name
        bv = b.name
      } else if (sortKey === 'chapters') {
        av = a.stats.chapters
        bv = b.stats.chapters
      } else if (sortKey === 'createdAt') {
        av = a.id
        bv = b.id
      } else {
        av = a.updatedAt
        bv = b.updatedAt
      }

      if (typeof av === 'number' && typeof bv === 'number') {
        return sortOrder === 'asc' ? av - bv : bv - av
      }
      const res = String(av).localeCompare(String(bv))
      return sortOrder === 'asc' ? res : -res
    })

    return next
  }, [projects, search, filterTab, sortKey, sortOrder])

  const handleSelectProject = (id: string) => {
    setSelectedProjectId(id)
  }

  const handleToggleSelect = (id: string, checked: boolean) => {
    setSelectedIds((prev) =>
      checked ? Array.from(new Set([...prev, id])) : prev.filter((x) => x !== id)
    )
  }

  const handleBatchDelete = async () => {
    if (!selectedIds.length) return
    try {
      await Promise.all(
        selectedIds.map((id) =>
          StudioProjectsService.deleteProjectApiV1StudioProjectsProjectIdDelete({ projectId: id }),
        ),
      )
      setProjects((prev) =>
        Array.isArray(prev) ? prev.filter((p) => !selectedIds.includes(p.id)) : prev
      )
      setSelectedIds([])
      message.success('已批量删除选中项目')
    } catch {
      message.error('批量删除失败')
    }
  }

  const handleOpenCreate = () => {
    form.resetFields()
    form.setFieldsValue({
      style: '现实主义',
      seed: Math.floor(Math.random() * 99999),
      unifyStyle: true,
    })
    setCreateModalOpen(true)
  }

  const handleCreateSubmit = async (values: {
    name: string
    description?: string
    style: string
    seed: number
    unifyStyle: boolean
  }) => {
    try {
      const createdId = newProjectId()
      const res = await StudioProjectsService.createProjectApiV1StudioProjectsPost({
        requestBody: {
          id: createdId,
          name: values.name,
          description: values.description ?? '',
          style: values.style as ProjectStyle,
          seed: values.seed,
          unify_style: values.unifyStyle,
          progress: 0,
        },
      })
      const created = res.data
      if (!created) throw new Error('empty project')
      const ui = toUIProject(created)
      message.success('项目创建成功')
      setCreateModalOpen(false)
      setProjects((prev) => (Array.isArray(prev) ? [...prev, ui] : [ui]))
      navigate(`/projects/${ui.id}`)
    } catch {
      message.error('创建失败')
    }
  }

  const handleOpenEdit = (e: React.MouseEvent, p: Project) => {
    e.stopPropagation()
    setEditingProject(p)
    editForm.setFieldsValue({
      name: p.name,
      description: p.description,
      style: p.style,
      seed: p.seed,
      unifyStyle: p.unifyStyle,
    })
    setEditModalOpen(true)
  }

  const handleEditSubmit = async (values: {
    name: string
    description?: string
    style: string
    seed: number
    unifyStyle: boolean
  }) => {
    if (!editingProject) return
    try {
      const res = await StudioProjectsService.updateProjectApiV1StudioProjectsProjectIdPatch({
        projectId: editingProject.id,
        requestBody: {
          name: values.name,
          description: values.description ?? '',
          style: values.style as ProjectStyle,
          seed: values.seed,
          unify_style: values.unifyStyle,
        },
      })
      const updated = res.data
      if (!updated) throw new Error('empty project')
      const ui = toUIProject(updated)
      message.success('项目已更新')
      setEditModalOpen(false)
      setEditingProject(null)
      setProjects((prev) =>
        Array.isArray(prev) ? prev.map((x) => (x.id === ui.id ? ui : x)) : prev
      )
    } catch {
      message.error('更新失败')
    }
  }

  const handleDelete = async (projectId: string) => {
    try {
      await StudioProjectsService.deleteProjectApiV1StudioProjectsProjectIdDelete({ projectId })
      message.success('已删除')
      setProjects((prev) => (Array.isArray(prev) ? prev.filter((p) => p.id !== projectId) : []))
    } catch {
      message.error('删除失败')
    }
  }

  const renderStatusTag = (p: Project) => {
    const status = getProjectStatus(p)
    if (status === 'completed') return <Tag color="green">已完成</Tag>
    if (status === 'draft') return <Tag color="default">草稿</Tag>
    return <Tag color="orange">进行中</Tag>
  }

  /**
   * 根据项目 ID 生成稳定的浅色渐变背景，避免深色背景。
   */
  const getLightGradientByProjectId = (id: string): string => {
    const gradients = [
      'from-sky-100 via-sky-50 to-white',
      'from-emerald-100 via-emerald-50 to-white',
      'from-indigo-100 via-indigo-50 to-white',
      'from-amber-100 via-amber-50 to-white',
      'from-rose-100 via-rose-50 to-white',
      'from-violet-100 via-violet-50 to-white',
      'from-teal-100 via-teal-50 to-white',
    ]

    let hash = 0
    for (let i = 0; i < id.length; i += 1) {
      hash = (hash * 31 + id.charCodeAt(i)) >>> 0
    }

    const index = hash % gradients.length
    return gradients[index]
  }

  const selectedProject = filteredSorted.find((p) => p.id === selectedProjectId) ?? filteredSorted[0]

  const renderCard = (p: Project) => {
    const status = getProjectStatus(p)
    const mainActionLabel =
      status === 'completed'
        ? '继续剪辑'
        : p.progress > 0
          ? '继续拍摄'
          : '进入项目'

    const isSelected = selectedProject && selectedProject.id === p.id
    const isChecked = selectedIds.includes(p.id)

    return (
      <Card
        key={p.id}
        hoverable
        loading={loading}
        size="small"
        className={`h-full cursor-pointer transition-all duration-200 ${
          isSelected ? 'ring-2 ring-indigo-500 ring-offset-1' : 'hover:shadow-lg'
        }`}
        bodyStyle={{ padding: '12px' }}
        onClick={() => {
          handleSelectProject(p.id)
          if (!multiSelectMode) {
            navigate(`/projects/${p.id}`)
          }
        }}
        onMouseEnter={() => handleSelectProject(p.id)}
      >
        <div
          className={`relative mb-2 rounded-md bg-gradient-to-r ${getLightGradientByProjectId(
            p.id,
          )} text-gray-900 p-2.5 overflow-hidden`}
        >
          <div className="flex justify-between items-start gap-2">
            <div className="min-w-0">
              <div className="text-xs text-gray-500 mb-0.5">{p.style}</div>
              <div className="text-base font-semibold truncate text-gray-900">{p.name}</div>
              <div className="text-[11px] text-gray-500 truncate">
                {p.updatedAt}
              </div>
            </div>
            <div className="flex flex-col items-end gap-2">
              {renderStatusTag(p)}
              {multiSelectMode && (
                <input
                  type="checkbox"
                  className="cursor-pointer"
                  checked={isChecked}
                  onChange={(e) => {
                    e.stopPropagation()
                    handleToggleSelect(p.id, e.target.checked)
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              )}
            </div>
          </div>
        </div>

        <p className="text-gray-600 text-xs mb-2 line-clamp-2 min-h-[2rem]">
          {p.description}
        </p>

        <div className="mb-2">
          <div className="flex justify-between text-[11px] mb-0.5 text-gray-500">
            <span>进度</span>
            <span>{p.progress}%</span>
          </div>
          <Progress
            percent={p.progress}
            size="small"
            showInfo={false}
            strokeColor={{ from: '#6366f1', to: '#a855f7' }}
          />
        </div>

        <Row gutter={6} className="mb-2">
          <Col span={6}>
            <Statistic title={<span className="text-[11px]">章节</span>} value={p.stats.chapters} valueStyle={{ fontSize: '13px' }} />
          </Col>
          <Col span={6}>
            <Statistic title={<span className="text-[11px]">角色</span>} value={p.stats.roles} valueStyle={{ fontSize: '13px' }} />
          </Col>
          <Col span={6}>
            <Statistic title={<span className="text-[11px]">场景</span>} value={p.stats.scenes} valueStyle={{ fontSize: '13px' }} />
          </Col>
          <Col span={6}>
            <Statistic title={<span className="text-[11px]">道具</span>} value={p.stats.props} valueStyle={{ fontSize: '13px' }} />
          </Col>
        </Row>

        <div className="mt-1.5 pt-2 border-t border-gray-100 flex items-center justify-between gap-1">
          <span className="text-[11px] text-gray-500 truncate">{p.updatedAt}</span>
          <Space size="small" onClick={(e) => e.stopPropagation()}>
            <Button
              type="primary"
              size="small"
              icon={<EnterOutlined />}
              onClick={() => navigate(`/projects/${p.id}`)}
            >
              {mainActionLabel}
            </Button>
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={(e) => handleOpenEdit(e, p)}
            />
            <Popconfirm
              title="确定删除该项目？"
              description="删除后无法恢复，相关章节与素材将不再关联。"
              onConfirm={() => handleDelete(p.id)}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button type="text" size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        </div>
      </Card>
    )
  }

  return (
    <div className="min-h-0 flex-1 flex flex-col overflow-hidden">
      <div className="flex-shrink-0 space-y-3 pb-3">
      <div className="sticky top-0 z-10 pb-2 bg-gradient-to-b from-[rgba(249,250,251,0.96)] to-[rgba(249,250,251,0.9)] backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Space wrap size="middle" className="flex-1 min-w-[260px]">
            <Input.Search
              placeholder="搜索项目名称或描述"
              allowClear
              className="w-72 max-w-full"
              onSearch={setSearch}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Space size="small" wrap>
              <Button
                type={filterTab === 'all' ? 'primary' : 'text'}
                size="small"
                onClick={() => setFilterTab('all')}
              >
                全部
              </Button>
              <Button
                type={filterTab === 'inProgress' ? 'primary' : 'text'}
                size="small"
                onClick={() => setFilterTab('inProgress')}
              >
                进行中
              </Button>
              <Button
                type={filterTab === 'completed' ? 'primary' : 'text'}
                size="small"
                onClick={() => setFilterTab('completed')}
              >
                已完成
              </Button>
              <Button
                type={filterTab === 'mine' ? 'primary' : 'text'}
                size="small"
                onClick={() => setFilterTab('mine')}
              >
                我创建的
              </Button>
              <Button
                type={filterTab === 'recent' ? 'primary' : 'text'}
                size="small"
                onClick={() => setFilterTab('recent')}
              >
                最近打开
              </Button>
            </Space>
          </Space>

          <Space size="middle" wrap>
            <Space size="small">
              <span className="text-xs text-gray-500">排序</span>
              <Select
                size="small"
                value={sortKey}
                style={{ width: 140 }}
                onChange={(value: SortKey) => setSortKey(value)}
                options={[
                  { label: '最近更新', value: 'updatedAt' },
                  { label: '名称 A-Z', value: 'name' },
                  { label: '章节数量', value: 'chapters' },
                ]}
              />
              <Button
                size="small"
                type="text"
                onClick={() => setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'))}
              >
                {sortOrder === 'asc' ? '↑' : '↓'}
              </Button>
            </Space>

            <Space size="small">
              <span className="text-xs text-gray-500">视图</span>
              <Button
                size="small"
                type={viewMode === 'grid' ? 'primary' : 'text'}
                icon={<AppstoreOutlined />}
                onClick={() => setViewMode('grid')}
              />
              <Button
                size="small"
                type={viewMode === 'compact' ? 'primary' : 'text'}
                icon={<BarsOutlined />}
                onClick={() => setViewMode('compact')}
              />
              <Button
                size="small"
                type={viewMode === 'large' ? 'primary' : 'text'}
                icon={<UnorderedListOutlined />}
                onClick={() => setViewMode('large')}
              />
            </Space>

            <Space size="small">
              <Button
                size="small"
                type={multiSelectMode ? 'primary' : 'text'}
                onClick={() => {
                  setMultiSelectMode((prev) => !prev)
                  setSelectedIds([])
                }}
              >
                批量
              </Button>
              {multiSelectMode && (
                <Popconfirm
                  title="批量删除项目"
                  description="确定删除选中的所有项目？该操作不可恢复。"
                  onConfirm={handleBatchDelete}
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  disabled={!selectedIds.length}
                >
                  <Button size="small" danger disabled={!selectedIds.length}>
                    删除选中
                  </Button>
                </Popconfirm>
              )}
            </Space>

            <Button type="primary" icon={<PlusOutlined />} onClick={handleOpenCreate}>
              新建项目
            </Button>
          </Space>
        </div>
      </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
      <Row gutter={12}>
        <Col xs={24} lg={18}>
          <Row gutter={[12, 12]}>
            {!loading && filteredSorted.length === 0 && (
              <Col span={24}>
                <Card>
                  <div className="text-center text-gray-500 py-12">
                    {search ? '没有匹配的项目' : '暂无项目，点击「新建项目」开始'}
                  </div>
                </Card>
              </Col>
            )}
            {filteredSorted.map((p) => (
              <Col
                key={p.id}
                xs={24}
                sm={viewMode === 'grid' ? 12 : 24}
                md={viewMode === 'grid' ? 8 : 24}
                lg={viewMode === 'grid' ? 6 : 24}
                xl={viewMode === 'grid' ? 6 : 24}
              >
                {renderCard(p)}
              </Col>
            ))}
          </Row>
        </Col>

        <Col xs={24} lg={6} className="flex-shrink-0">
          <div className="h-full">
            <Card
              size="small"
              title="项目速览"
              className="mb-2"
            >
              {selectedProject ? (
                <div className="space-y-3">
                  <div>
                    <div className="text-xs text-gray-500 mb-1">项目名称</div>
                    <div className="font-medium">{selectedProject.name}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">简介</div>
                    <div className="text-sm text-gray-600 line-clamp-3">
                      {selectedProject.description || '暂无描述'}
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-xs text-gray-500">
                    <span>视频风格：{selectedProject.style}</span>
                    <span>种子：{selectedProject.seed}</span>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-1">进度</div>
                    <Progress
                      percent={selectedProject.progress}
                      strokeColor={{ from: '#6366f1', to: '#22c55e' }}
                    />
                  </div>
                  <Row gutter={8}>
                    <Col span={12}>
                      <Statistic title="章节" value={selectedProject.stats.chapters} />
                    </Col>
                    <Col span={12}>
                      <Statistic title="素材" value={selectedProject.stats.props} />
                    </Col>
                  </Row>
                  <Button
                    type="primary"
                    block
                    icon={<EnterOutlined />}
                    onClick={() => navigate(`/projects/${selectedProject.id}`)}
                  >
                    进入章节工作台
                  </Button>
                </div>
              ) : (
                <div className="text-gray-500 text-sm py-6 text-center">
                  将鼠标悬停在项目卡片上查看详情
                </div>
              )}
            </Card>
          </div>
        </Col>
      </Row>
      </div>

      <Modal
        title="新建短剧项目"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        footer={null}
        width={520}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreateSubmit}
          initialValues={{
            style: '现实主义',
            seed: Math.floor(Math.random() * 99999),
            visual_style: '动漫',
            unifyStyle: true,
          }}
        >
          <Form.Item
            name="name"
            label="项目名称"
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input placeholder="例如：现实都市爱情短剧" />
          </Form.Item>
          <Form.Item name="description" label="项目简介（选填）">
            <Input.TextArea rows={4} placeholder="项目简介与风格说明，建议 80–120 字" />
          </Form.Item>
          <Form.Item name="style" label="视频风格" rules={[{ required: true }]}>
            <Select
              options={[
                { value: '现实主义', label: '现实主义' },
                { value: '科幻', label: '科幻' },
                { value: '古风', label: '古风' },
                { value: '都市喜剧', label: '都市喜剧' },
              ]}
            />
          </Form.Item>
          <Form.Item name="visual_style" label="视觉风格" rules={[{ required: true }]}>
            <Select
              options={[
                { value: '动漫', label: '动漫' },
                { value: '真人', label: '真人' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="seed"
            label="全局种子值"
            tooltip="固定种子可确保整部短剧视觉调性一致"
          >
            <InputNumber min={0} className="w-full" />
          </Form.Item>
          <Form.Item
            name="unifyStyle"
            label="所有章节强制继承此风格"
            valuePropName="checked"
            tooltip="开启后所有章节继承项目风格"
          >
            <Switch />
          </Form.Item>
          <Form.Item className="mb-0">
            <Space>
              <Button onClick={() => setCreateModalOpen(false)}>取消</Button>
              <Button type="primary" htmlType="submit">
                创建并进入
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑项目"
        open={editModalOpen}
        onCancel={() => { setEditModalOpen(false); setEditingProject(null) }}
        footer={null}
        width={520}
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={handleEditSubmit}
          initialValues={{ style: '现实主义', unifyStyle: true }}
        >
          <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="项目名称" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="项目简介与风格说明" />
          </Form.Item>
          <Form.Item name="style" label="视频风格" rules={[{ required: true }]}>
            <Select
              options={[
                { value: '现实主义', label: '现实主义' },
              ]}
            />
          </Form.Item>
          <Form.Item name="seed" label="全局种子值" tooltip="固定种子可确保整部短剧视觉调性一致">
            <InputNumber min={0} className="w-full" />
          </Form.Item>
          <Form.Item name="unifyStyle" label="风格统一" valuePropName="checked" tooltip="开启后所有章节继承项目风格">
            <Switch />
          </Form.Item>
          <Form.Item className="mb-0">
            <Space>
              <Button onClick={() => { setEditModalOpen(false); setEditingProject(null) }}>取消</Button>
              <Button type="primary" htmlType="submit">保存</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default ProjectLobby
