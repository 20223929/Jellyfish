import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Badge,
  Button,
  Card,
  Divider,
  Dropdown,
  Image,
  Input,
  Layout,
  Modal,
  Radio,
  Segmented,
  Select,
  Slider,
  Spin,
  Space,
  Switch,
  Tabs,
  Tag,
  Tooltip,
  message,
} from 'antd'
import {
  AppstoreOutlined,
  ArrowLeftOutlined,
  CaretLeftOutlined,
  CaretRightOutlined,
  CameraOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CustomerServiceOutlined,
  DeleteOutlined,
  DoubleLeftOutlined,
  DoubleRightOutlined,
  DownOutlined,
  EditOutlined,
  ExportOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  FileExcelOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  LinkOutlined,
  MergeCellsOutlined,
  PauseCircleOutlined,
  PictureOutlined,
  PlayCircleOutlined,
  SaveOutlined,
  ScissorOutlined,
  SettingOutlined,
  SoundOutlined,
  TagOutlined,
  ToolOutlined,
  VideoCameraOutlined,
  ThunderboltOutlined,
  UploadOutlined,
  VideoCameraAddOutlined,
  PlusOutlined,
  UserOutlined,
  DownloadOutlined,
} from '@ant-design/icons'
import { useParams, Link } from 'react-router-dom'
import {
  FilmService,
  StudioChaptersService,
  StudioFilesService,
  StudioImageTasksService,
  StudioShotCharacterLinksService,
  StudioShotDetailsService,
  StudioShotDialogLinesService,
  StudioShotFrameImagesService,
  StudioShotLinksService,
  StudioShotsService,
} from '../../../services/generated'
import { StudioEntitiesApi } from '../../../services/studioEntities'
import type {
  CameraAngle,
  CameraMovement,
  CameraShotType,
  ChapterRead,
  ProjectActorLinkRead,
  ProjectCostumeLinkRead,
  ShotDetailRead,
  ShotDialogLineRead,
  ShotFrameImageRead,
  ShotCharacterLinkRead,
  ProjectPropLinkRead,
  ShotRead,
  ProjectSceneLinkRead,
  ShotStatus,
} from '../../../services/generated'
import { listTaskLinksNormalized } from '../../../services/filmTaskLinks'
import { buildFileDownloadUrl, resolveAssetUrl } from '../assets/utils'
import type { Chapter } from '../../../mocks/data'
import './chapterStudio.separation.css'

const { Sider, Content } = Layout
const { TextArea } = Input

const FRAME_FILE_TAG_ADOPT = '采用'
const FRAME_FILE_TAG_ABANDON = '废弃'

function normalizeFrameExclusiveTags(tags: string[]): string[] {
  const cleaned = (tags || []).map((x) => String(x ?? '').trim()).filter(Boolean)
  const hasAdopt = cleaned.includes(FRAME_FILE_TAG_ADOPT)
  const hasAbandon = cleaned.includes(FRAME_FILE_TAG_ABANDON)
  const rest = cleaned.filter((t) => t !== FRAME_FILE_TAG_ADOPT && t !== FRAME_FILE_TAG_ABANDON)
  if (hasAdopt && !hasAbandon) return [FRAME_FILE_TAG_ADOPT, ...rest]
  if (!hasAdopt && hasAbandon) return [FRAME_FILE_TAG_ABANDON, ...rest]
  // 两者都没有或同时存在：同时存在时默认保留“采用”
  if (hasAdopt && hasAbandon) return [FRAME_FILE_TAG_ADOPT, ...rest]
  return rest
}

type InspectorMode = 'push' | 'overlay'
type ShotFilter = 'all' | 'pending' | 'ready' | 'hidden' | 'problem'

type StudioShot = ShotRead & {
  hidden?: boolean
  hasProblem?: boolean
  hasSpeech?: boolean
  hasMusic?: boolean
}

type LayoutPrefs = {
  leftWidth: number
  rightWidth: number
  inspectorOpen: boolean
  inspectorMode: InspectorMode
  autoOpenInspector: boolean
  timelineCollapsed: boolean
}

type KeyframeCardState = {
  loading: boolean
  taskStatus: string | null
  taskId: string | null
  thumbs: Array<{ linkId: number; fileId: string; thumbUrl: string }>
  modalOpen: boolean
  applyingFileId: string | null
}

const LAYOUT_STORAGE_KEY = 'jellyfish_chapter_studio_layout_v1'
type PromptFrameType = 'first' | 'key' | 'last'

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n))
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function reorder<T>(list: T[], startIndex: number, endIndex: number) {
  const result = [...list]
  const [removed] = result.splice(startIndex, 1)
  result.splice(endIndex, 0, removed)
  return result
}

function isTypingTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true
  if (target.isContentEditable) return true
  return Boolean(target.closest('[contenteditable="true"]'))
}

function toUIChapter(c: ChapterRead): Chapter {
  return {
    id: c.id,
    projectId: c.project_id,
    index: c.index,
    title: c.title,
    summary: c.summary ?? '',
    storyboardCount: c.shot_count ?? c.storyboard_count ?? 0,
    status: c.status ?? 'draft',
    updatedAt: new Date().toISOString(),
  }
}

const CAMERA_SHOT_OPTIONS: { value: CameraShotType; label: string }[] = [
  { value: 'ECU', label: '极特写' },
  { value: 'CU', label: '特写' },
  { value: 'MCU', label: '中近景' },
  { value: 'MS', label: '中景' },
  { value: 'MLS', label: '中远景' },
  { value: 'LS', label: '远景' },
  { value: 'ELS', label: '大全景' },
]

const CAMERA_ANGLE_OPTIONS: { value: CameraAngle; label: string }[] = [
  { value: 'EYE_LEVEL', label: '平视' },
  { value: 'HIGH_ANGLE', label: '俯视' },
  { value: 'LOW_ANGLE', label: '仰视' },
  { value: 'BIRD_EYE', label: '鸟瞰' },
  { value: 'DUTCH', label: '倾斜' },
  { value: 'OVER_SHOULDER', label: '越肩' },
]

const CAMERA_MOVEMENT_OPTIONS: { value: CameraMovement; label: string }[] = [
  { value: 'STATIC', label: '固定' },
  { value: 'PAN', label: '摇镜' },
  { value: 'TILT', label: '俯仰' },
  { value: 'DOLLY_IN', label: '推进' },
  { value: 'DOLLY_OUT', label: '拉出' },
  { value: 'TRACK', label: '跟拍' },
  { value: 'CRANE', label: '升降' },
  { value: 'HANDHELD', label: '手持' },
  { value: 'STEADICAM', label: '稳定器' },
  { value: 'ZOOM_IN', label: '变焦推' },
  { value: 'ZOOM_OUT', label: '变焦拉' },
]

function useLocalStoragePrefs() {
  const [prefs, setPrefs] = useState<LayoutPrefs>(() => {
    try {
      const raw = window.localStorage.getItem(LAYOUT_STORAGE_KEY)
      if (!raw) {
        return {
          leftWidth: 280,
          rightWidth: 420,
          inspectorOpen: false,
          inspectorMode: 'push',
          autoOpenInspector: true,
          timelineCollapsed: false,
        }
      }
      const parsed = JSON.parse(raw) as Partial<LayoutPrefs>
      return {
        leftWidth: typeof parsed.leftWidth === 'number' ? parsed.leftWidth : 280,
        rightWidth: typeof parsed.rightWidth === 'number' ? parsed.rightWidth : 420,
        inspectorOpen: typeof parsed.inspectorOpen === 'boolean' ? parsed.inspectorOpen : false,
        inspectorMode: parsed.inspectorMode === 'overlay' ? 'overlay' : 'push',
        autoOpenInspector: typeof parsed.autoOpenInspector === 'boolean' ? parsed.autoOpenInspector : true,
        timelineCollapsed: typeof parsed.timelineCollapsed === 'boolean' ? parsed.timelineCollapsed : false,
      }
    } catch {
      return {
        leftWidth: 280,
        rightWidth: 420,
        inspectorOpen: false,
        inspectorMode: 'push',
        autoOpenInspector: true,
        timelineCollapsed: false,
      }
    }
  })

  useEffect(() => {
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(prefs))
  }, [prefs])

  return [prefs, setPrefs] as const
}

const ChapterStudio: React.FC = () => {
  const { projectId, chapterId } = useParams<{
    projectId?: string
    chapterId?: string
  }>()
  const [chapter, setChapter] = useState<Chapter | null>(null)
  const [shots, setShots] = useState<StudioShot[]>([])
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null)
  const [selectedShotIds, setSelectedShotIds] = useState<string[]>([])
  const lastSelectedIndexRef = useRef<number>(-1)
  const [shotDetail, setShotDetail] = useState<ShotDetailRead | null>(null)
  const [dialogLines, setDialogLines] = useState<ShotDialogLineRead[]>([])
  const [frameImages, setFrameImages] = useState<ShotFrameImageRead[]>([])
  const [sceneLinks, setSceneLinks] = useState<ProjectSceneLinkRead[]>([])
  const [actorImageLinks, setActorImageLinks] = useState<ProjectActorLinkRead[]>([])
  const [propLinks, setPropLinks] = useState<ProjectPropLinkRead[]>([])
  const [costumeLinks, setCostumeLinks] = useState<ProjectCostumeLinkRead[]>([])
  const [shotCharacterLinks, setShotCharacterLinks] = useState<ShotCharacterLinkRead[]>([])
  const [shotDurations, setShotDurations] = useState<Record<string, number>>({})
  const [loadingShots, setLoadingShots] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [prefs, setPrefs] = useLocalStoragePrefs()
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const saveTimerRef = useRef<number | null>(null)
  const cameraPatchSeqRef = useRef(0)
  const [cameraUpdating, setCameraUpdating] = useState(false)
  const [promptAssetsUpdating, setPromptAssetsUpdating] = useState(false)

  const [frameTab, setFrameTab] = useState<'head' | 'keyframes' | 'tail' | 'compare'>('keyframes')
  const [frameFileTagsMap, setFrameFileTagsMap] = useState<Record<string, string[]>>({})
  const [frameFileTagsLoading, setFrameFileTagsLoading] = useState(false)
  const [playbackRate, setPlaybackRate] = useState(1)
  const [loopCurrent, setLoopCurrent] = useState(false)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [previewVideoFileId, setPreviewVideoFileId] = useState<string | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [videoDuration, setVideoDuration] = useState(0)
  const [videoTime, setVideoTime] = useState(0)

  const [filter, setFilter] = useState<ShotFilter>('all')
  const [exportModalOpen, setExportModalOpen] = useState(false)
  const [exportFormat, setExportFormat] = useState<'excel' | 'json' | 'pdf'>('excel')
  const [editingTitleId, setEditingTitleId] = useState<string | null>(null)
  const [editingTitleValue, setEditingTitleValue] = useState('')
  const [draggingShotId, setDraggingShotId] = useState<string | null>(null)
  const [dragOverShotId, setDragOverShotId] = useState<string | null>(null)
  const [isResizing, setIsResizing] = useState(false)

  const containerRef = useRef<HTMLDivElement | null>(null)
  const dragStateRef = useRef<null | { type: 'left' | 'right'; startX: number; startLeft: number; startRight: number }>(null)
  const resizeRafRef = useRef<number | null>(null)
  const pendingResizeRef = useRef<null | { leftWidth?: number; rightWidth?: number }>(null)
  const showPreviewMinimizeButton = false
  const showPreviewFrameSegmented = false
  const showChapterTimeline = false

  const hiddenKey = useMemo(() => (chapterId ? `jellyfish_hidden_shots_${chapterId}` : null), [chapterId])
  const hiddenIds = useMemo(() => {
    if (!hiddenKey) return new Set<string>()
    try {
      const raw = window.localStorage.getItem(hiddenKey)
      const arr = raw ? (JSON.parse(raw) as unknown) : []
      return new Set(Array.isArray(arr) ? (arr.filter((x) => typeof x === 'string') as string[]) : [])
    } catch {
      return new Set<string>()
    }
  }, [hiddenKey])

  const saveHiddenIds = (next: Set<string>) => {
    if (!hiddenKey) return
    try {
      window.localStorage.setItem(hiddenKey, JSON.stringify(Array.from(next)))
    } catch {
      // ignore
    }
  }

  const toggleHiddenShots = (ids: string[]) => {
    if (!hiddenKey) return
    const next = new Set(hiddenIds)
    ids.forEach((id) => {
      if (next.has(id)) next.delete(id)
      else next.add(id)
    })
    saveHiddenIds(next)
    setShots((prev) => prev.map((s) => (ids.includes(s.id) ? { ...s, hidden: next.has(s.id) } : s)))
  }

  const loadShots = async () => {
    if (!chapterId) return
    setLoadingShots(true)
    try {
      const res = await StudioShotsService.listShotsApiV1StudioShotsGet({
        chapterId,
        page: 1,
        pageSize: 100,
        order: 'index',
        isDesc: false,
      })
      const arr = res.data?.items ?? []
      // 给分镜补充一些“工作台态”的展示字段（后续可由后端返回）
      const enriched: StudioShot[] = arr
        .slice()
        .sort((a, b) => a.index - b.index)
        .map((s, idx) => ({
          ...s,
          hidden: hiddenIds.has(s.id),
          hasProblem: idx === 4,
          hasSpeech: true,
          hasMusic: idx % 3 !== 0,
        }))

      setShots(enriched)

      const selectedExists = selectedShotId ? enriched.some((s) => s.id === selectedShotId) : false
      if (!selectedShotId || !selectedExists) {
        const firstUnfinished = enriched.find((s) => !s.hidden && s.status !== 'ready')
        const firstVisible = enriched.find((s) => !s.hidden)
        setSelectedShotId((firstUnfinished ?? firstVisible ?? enriched[0])?.id ?? null)
      }
    } catch {
      message.error('加载分镜失败')
    } finally {
      setLoadingShots(false)
    }
  }

  const patchShotInList = (shotId: string, patch: Partial<StudioShot>) => {
    setShots((prev) => prev.map((s) => (s.id === shotId ? { ...s, ...patch } : s)))
  }

  const updateShotTitleInOps = async (shotId: string, title: string) => {
    try {
      const res = await StudioShotsService.updateShotApiV1StudioShotsShotIdPatch({
        shotId,
        requestBody: { title },
      } as any)
      if (res.data) patchShotInList(shotId, res.data as any)
      message.success('标题已保存')
    } catch {
      message.error('保存标题失败')
    }
  }

  const updateShotScriptExcerptInOps = async (shotId: string, script_excerpt: string) => {
    try {
      const res = await StudioShotsService.updateShotApiV1StudioShotsShotIdPatch({
        shotId,
        requestBody: { script_excerpt },
      } as any)
      if (res.data) patchShotInList(shotId, res.data as any)
      message.success('备注已保存')
    } catch {
      message.error('保存备注失败')
    }
  }

  const deleteShotFromOps = async (shotId: string) => {
    try {
      await StudioShotsService.deleteShotApiV1StudioShotsShotIdDelete({ shotId })
      await loadShots()
      message.success('已删除')
    } catch {
      message.error('删除失败')
    }
  }

  const loadChapter = async () => {
    if (!chapterId) return
    try {
      const res = await StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId })
      const data = res.data
      if (!data) {
        setChapter(null)
        return
      }
      setChapter(toUIChapter(data))
    } catch {
      // 章节信息仅用于标题展示，失败不阻断工作台
      setChapter(null)
    }
  }

  useEffect(() => {
    void loadShots()
    void loadChapter()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterId, projectId])

  useEffect(() => {
    if (!selectedShotId) {
      setShotDetail(null)
      setDialogLines([])
      setFrameImages([])
      setSceneLinks([])
      setActorImageLinks([])
      setPropLinks([])
      setCostumeLinks([])
      setShotCharacterLinks([])
      return
    }
    setLoadingDetail(true)
    Promise.all([
      StudioShotDetailsService.getShotDetailApiV1StudioShotDetailsShotIdGet({ shotId: selectedShotId }).then((r: any) => r.data ?? null),
      StudioShotDialogLinesService.listShotDialogLinesApiV1StudioShotDialogLinesGet({
        shotDetailId: selectedShotId,
        q: null,
        order: 'index',
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => r.data?.items ?? []),
      StudioShotFrameImagesService.listShotFrameImagesApiV1StudioShotFrameImagesGet({
        shotDetailId: selectedShotId,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => r.data?.items ?? []),
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'scene',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId: selectedShotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => r.data?.items ?? []),
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'actor',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId: selectedShotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => r.data?.items ?? []),
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'prop',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId: selectedShotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => r.data?.items ?? []),
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'costume',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId: selectedShotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => r.data?.items ?? []),
      StudioShotCharacterLinksService.listShotCharacterLinksApiV1StudioShotCharacterLinksGet({
        shotId: selectedShotId,
      }).then((r: any) => (r.data ?? []) as ShotCharacterLinkRead[]),
    ])
      .then(([detail, dialogs, frames, scenes, actors, props, costumes, shotCharacters]) => {
        setShotDetail(detail)
        lastSavedDetailRef.current = detail
        setDialogLines(dialogs)
        setFrameImages(frames)
        setSceneLinks(scenes)
        setActorImageLinks(actors)
        setPropLinks(props)
        setCostumeLinks(costumes)
        setShotCharacterLinks(shotCharacters)
        if (detail?.duration != null) {
          setShotDurations((prev) => ({ ...prev, [selectedShotId]: detail.duration ?? 0 }))
        }
      })
      .catch(() => message.error('加载分镜详情失败'))
      .finally(() => setLoadingDetail(false))
  }, [selectedShotId])

  useEffect(() => {
    // 选中分镜时同步多选的“主选中项”
    if (!selectedShotId) return
    if (selectedShotIds.includes(selectedShotId)) return
    setSelectedShotIds([selectedShotId])
  }, [selectedShotId, selectedShotIds])

  const selectedShot = useMemo(() => shots.find((s) => s.id === selectedShotId) ?? null, [shots, selectedShotId])
  const currentPreviewVideoFileId = previewVideoFileId || selectedShot?.generated_video_file_id || null
  const currentPreviewVideoUrl = currentPreviewVideoFileId ? buildFileDownloadUrl(currentPreviewVideoFileId) ?? '' : ''

  useEffect(() => {
    // 切换分镜时：主预览区视频跟随分镜（清空手动选择的预览视频）
    setPreviewVideoFileId(null)
  }, [selectedShotId])

  const refreshDialogLines = async (shotId: string) => {
    const res = await StudioShotDialogLinesService.listShotDialogLinesApiV1StudioShotDialogLinesGet({
      shotDetailId: shotId,
      q: null,
      order: 'index',
      isDesc: false,
      page: 1,
      pageSize: 100,
    })
    setDialogLines(res.data?.items ?? [])
  }

  const addDialogLine = async (text: string) => {
    if (!selectedShotId) return
    const v = text.trim()
    if (!v) return
    await StudioShotDialogLinesService.createShotDialogLineApiV1StudioShotDialogLinesPost({
      requestBody: {
        shot_detail_id: selectedShotId,
        text: v,
        line_mode: 'DIALOGUE',
      },
    })
    await refreshDialogLines(selectedShotId)
  }

  const deleteDialogLine = async (lineId: number) => {
    if (!selectedShotId) return
    await StudioShotDialogLinesService.deleteShotDialogLineApiV1StudioShotDialogLinesLineIdDelete({ lineId })
    await refreshDialogLines(selectedShotId)
  }

  const refreshPromptAssetLinks = async (shotId: string) => {
    const [scenes, actors, props, costumes] = await Promise.all([
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'scene',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => (r.data?.items ?? []) as ProjectSceneLinkRead[]),
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'actor',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => (r.data?.items ?? []) as ProjectActorLinkRead[]),
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'prop',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => (r.data?.items ?? []) as ProjectPropLinkRead[]),
      StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: 'costume',
        projectId: projectId ?? null,
        chapterId: chapterId ?? null,
        shotId,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 100,
      }).then((r: any) => (r.data?.items ?? []) as ProjectCostumeLinkRead[]),
    ])
    setSceneLinks(scenes)
    setActorImageLinks(actors)
    setPropLinks(props)
    setCostumeLinks(costumes)
  }

  const updatePromptProps = async (propIds: string[]) => {
    if (!selectedShotId || !projectId) return
    const next = Array.from(new Set(propIds.map((x) => x.trim()).filter(Boolean)))
    setPromptAssetsUpdating(true)
    try {
      const currentLinks = propLinks.filter((l) => (l.shot_id ?? null) === selectedShotId)
      await Promise.all(currentLinks.map((l) => StudioShotLinksService.deleteProjectPropLinkApiV1StudioShotLinksPropLinkIdDelete({ linkId: l.id })))
      await Promise.all(
        next.map((pid) =>
          StudioShotLinksService.createProjectPropLinkApiV1StudioShotLinksPropPost({
            requestBody: { project_id: projectId, chapter_id: chapterId ?? null, shot_id: selectedShotId, asset_id: pid },
          }),
        ),
      )
      await refreshPromptAssetLinks(selectedShotId)
    } catch {
      message.error('更新道具失败')
    } finally {
      setPromptAssetsUpdating(false)
    }
  }

  const updatePromptCostumes = async (costumeIds: string[]) => {
    if (!selectedShotId || !projectId) return
    const next = Array.from(new Set(costumeIds.map((x) => x.trim()).filter(Boolean)))
    setPromptAssetsUpdating(true)
    try {
      const currentLinks = costumeLinks.filter((l) => (l.shot_id ?? null) === selectedShotId)
      await Promise.all(currentLinks.map((l) => StudioShotLinksService.deleteProjectCostumeLinkApiV1StudioShotLinksCostumeLinkIdDelete({ linkId: l.id })))
      await Promise.all(
        next.map((cid) =>
          StudioShotLinksService.createProjectCostumeLinkApiV1StudioShotLinksCostumePost({
            requestBody: { project_id: projectId, chapter_id: chapterId ?? null, shot_id: selectedShotId, asset_id: cid },
          }),
        ),
      )
      await refreshPromptAssetLinks(selectedShotId)
    } catch {
      message.error('更新服装失败')
    } finally {
      setPromptAssetsUpdating(false)
    }
  }

  const updatePromptScene = async (sceneId?: string) => {
    if (!selectedShotId || !projectId) return
    setPromptAssetsUpdating(true)
    try {
      const currentLinks = sceneLinks.filter((l) => (l.shot_id ?? null) === selectedShotId)
      await Promise.all(currentLinks.map((l) => StudioShotLinksService.deleteProjectSceneLinkApiV1StudioShotLinksSceneLinkIdDelete({ linkId: l.id })))
      const nextSceneId = (sceneId ?? '').trim()
      if (nextSceneId) {
        await StudioShotLinksService.createProjectSceneLinkApiV1StudioShotLinksScenePost({
          requestBody: {
            project_id: projectId,
            chapter_id: chapterId ?? null,
            shot_id: selectedShotId,
            asset_id: nextSceneId,
          },
        })
      }
      await refreshPromptAssetLinks(selectedShotId)
      patchShotDetailLocal({ scene_id: nextSceneId || null })
    } catch {
      message.error('更新场景失败')
    } finally {
      setPromptAssetsUpdating(false)
    }
  }

  const updatePromptActors = async (actorIds: string[]) => {
    if (!selectedShotId) return
    const next = Array.from(new Set(actorIds.map((x) => x.trim()).filter(Boolean)))
    const current = shotCharacterLinks
      .slice()
      .sort((a, b) => (a.index ?? 0) - (b.index ?? 0))
      .map((x) => x.character_id)
    const removed = current.filter((id) => !next.includes(id))
    if (removed.length > 0) {
      message.warning('当前接口暂不支持移除已关联角色，仅会新增或重排')
    }
    if (next.length === 0) return
    setPromptAssetsUpdating(true)
    try {
      await Promise.all(
        next.map((characterId, index) =>
          StudioShotCharacterLinksService.upsertShotCharacterLinkApiV1StudioShotCharacterLinksPost({
            requestBody: { shot_id: selectedShotId, character_id: characterId, index, note: '' },
          }),
        ),
      )
      const refreshed = await StudioShotCharacterLinksService.listShotCharacterLinksApiV1StudioShotCharacterLinksGet({ shotId: selectedShotId })
      setShotCharacterLinks((refreshed.data ?? []) as ShotCharacterLinkRead[])
    } catch {
      message.error('更新角色失败')
    } finally {
      setPromptAssetsUpdating(false)
    }
  }

  const generateFrameImageTask = async () => {
    if (!selectedShotId) return
    const target =
      (frameTab === 'head' && frameImages.find((x) => x.frame_type === 'first')) ||
      (frameTab === 'tail' && frameImages.find((x) => x.frame_type === 'last')) ||
      frameImages.find((x) => x.frame_type === 'key') ||
      frameImages[0]
    if (!target) {
      message.warning('请先添加一张分镜帧图（frame image）')
      return
    }
    const prompt =
      (target.frame_type === 'first'
        ? shotDetail?.first_frame_prompt
        : target.frame_type === 'last'
          ? shotDetail?.last_frame_prompt
          : shotDetail?.key_frame_prompt) ?? ''
    if (!prompt.trim()) {
      message.warning('请先生成或填写提示词')
      return
    }
    setGenerating(true)
    try {
      const linked = await StudioShotsService.listShotLinkedAssetsApiV1StudioShotsShotIdLinkedAssetsGet({
        shotId: selectedShotId,
        page: 1,
        pageSize: 100,
      })
      const items = (linked.data?.items ?? []) as any[]
      const extractFileId = (thumbnail?: string | null): string | null => {
        const v = (thumbnail || '').trim()
        if (!v) return null
        if (!v.includes('/') && !v.includes(':')) return v
        try {
          const url = new URL(v, typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
          const m = url.pathname.match(/\/api\/v1\/studio\/files\/([^/]+)\/download\/?$/)
          if (m?.[1]) return decodeURIComponent(m[1])
        } catch {
          // ignore
        }
        return null
      }
      const imagesPayload = items
        .map((x) => {
          const fileId = typeof x?.file_id === 'string' && x.file_id.trim() ? x.file_id.trim() : extractFileId(x?.thumbnail)
          return fileId
            ? {
                type: x?.type as any,
                id: String(x?.id ?? ''),
                name: String(x?.name ?? x?.id ?? ''),
                file_id: fileId,
              }
            : null
        })
        .filter(Boolean)
      await StudioImageTasksService.createShotFrameImageGenerationTaskApiV1StudioImageTasksShotShotIdFrameImageTasksPost({
        shotId: selectedShotId,
        requestBody: { frame_type: target.frame_type as any, model_id: null, prompt, images: imagesPayload } as any,
      })
      message.success('已创建生成任务')
    } catch {
      message.error('创建生成任务失败')
    } finally {
      setGenerating(false)
    }
  }

  const currentFrameSlot = useMemo(() => {
    if (frameTab === 'head') return frameImages.find((x) => x.frame_type === 'first') ?? null
    if (frameTab === 'tail') return frameImages.find((x) => x.frame_type === 'last') ?? null
    return frameImages.find((x) => x.frame_type === 'key') ?? frameImages[0] ?? null
  }, [frameImages, frameTab])

  const currentFrameFileId = useMemo(() => {
    const fid = currentFrameSlot?.file_id ?? null
    return fid ? String(fid) : null
  }, [currentFrameSlot?.file_id])

  const currentFrameFileTags = useMemo(() => {
    if (!currentFrameFileId) return []
    return frameFileTagsMap[currentFrameFileId] ?? []
  }, [currentFrameFileId, frameFileTagsMap])

  useEffect(() => {
    if (!currentFrameFileId) return
    if (frameFileTagsMap[currentFrameFileId]) return
    let canceled = false
    setFrameFileTagsLoading(true)
    void (async () => {
      try {
        const res = await StudioFilesService.getFileDetailApiV1StudioFilesFileIdGet({ fileId: currentFrameFileId })
        if (canceled) return
        const tagsRaw = Array.isArray((res.data as any)?.tags) ? ((res.data as any).tags as string[]).filter(Boolean) : []
        setFrameFileTagsMap((prev) => ({ ...prev, [currentFrameFileId]: normalizeFrameExclusiveTags(tagsRaw) }))
      } catch {
        if (!canceled) setFrameFileTagsMap((prev) => ({ ...prev, [currentFrameFileId]: [] }))
      } finally {
        if (!canceled) setFrameFileTagsLoading(false)
      }
    })()
    return () => {
      canceled = true
    }
  }, [currentFrameFileId, frameFileTagsMap])

  const updateCurrentFrameFileTags = useCallback(
    async (nextTags: string[]) => {
      if (!currentFrameFileId) return
      const cleaned = Array.from(
        new Set(
          (nextTags || [])
            .map((x) => String(x ?? '').trim())
            .filter((x) => x.length > 0),
        ),
      )
      const normalized = normalizeFrameExclusiveTags(cleaned)
      setFrameFileTagsLoading(true)
      setFrameFileTagsMap((prev) => ({ ...prev, [currentFrameFileId]: normalized }))
      try {
        await StudioFilesService.updateFileMetaApiV1StudioFilesFileIdPatch({
          fileId: currentFrameFileId,
          requestBody: { tags: normalized } as any,
        })
      } catch {
        message.error('更新标签失败')
      } finally {
        setFrameFileTagsLoading(false)
      }
    },
    [currentFrameFileId],
  )

  // 选中分镜后若开启自动展开属性面板：默认展开（尤其是未就绪分镜）
  useEffect(() => {
    if (!selectedShot) return
    if (!prefs.autoOpenInspector) return
    if (prefs.inspectorOpen) return
    // “若无视频则自动展开”：这里用 status !== ready 作为近似判定
    if (selectedShot.status !== 'ready') {
      setPrefs((p) => ({ ...p, inspectorOpen: true }))
    }
  }, [prefs.autoOpenInspector, prefs.inspectorOpen, selectedShot, setPrefs])

  const lastSavedDetailRef = useRef<ShotDetailRead | null>(null)

  const patchShotDetailLocal = (patch: Partial<ShotDetailRead>) => {
    setShotDetail((prev) => (prev ? { ...prev, ...patch } : prev))
  }

  const patchShotDetailImmediate = async (patch: Partial<ShotDetailRead>) => {
    if (!selectedShotId) return
    patchShotDetailLocal(patch)
    setCameraUpdating(true)
    const seq = ++cameraPatchSeqRef.current
    try {
      const r: any = await StudioShotDetailsService.updateShotDetailApiV1StudioShotDetailsShotIdPatch({
        shotId: selectedShotId,
        requestBody: patch as any,
      })
      if (seq !== cameraPatchSeqRef.current) return
      if (r.data) {
        setShotDetail(r.data)
        lastSavedDetailRef.current = r.data
        if (r.data.duration != null) {
          setShotDurations((m) => ({ ...m, [selectedShotId]: r.data?.duration ?? 0 }))
        }
      }
    } catch {
      if (seq !== cameraPatchSeqRef.current) return
      message.error('镜头语言更新失败')
    } finally {
      if (seq === cameraPatchSeqRef.current) setCameraUpdating(false)
    }
  }

  // 自动保存（防抖）：shotDetail 变更后 PATCH 到后端
  useEffect(() => {
    if (!selectedShotId || !shotDetail) return
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current)
    setSaving(true)
    saveTimerRef.current = window.setTimeout(() => {
      const prev = lastSavedDetailRef.current
      const next = shotDetail
      const patch: Record<string, unknown> = {}
      const assignIfChanged = <K extends keyof ShotDetailRead>(key: K) => {
        if (prev?.[key] !== next[key]) patch[key] = next[key] ?? null
      }
      assignIfChanged('scene_id')
      // 镜头语言字段（camera_shot/angle/movement/duration）走即时更新，不在此处防抖提交
      // array / object fields
      if (JSON.stringify(prev?.mood_tags ?? null) !== JSON.stringify(next.mood_tags ?? null)) patch.mood_tags = next.mood_tags ?? null
      assignIfChanged('atmosphere')
      assignIfChanged('follow_atmosphere')
      assignIfChanged('has_bgm')
      assignIfChanged('vfx_type')
      assignIfChanged('vfx_note')
      assignIfChanged('first_frame_prompt')
      assignIfChanged('key_frame_prompt')
      assignIfChanged('last_frame_prompt')

      const keys = Object.keys(patch)
      if (keys.length === 0) {
        setSaving(false)
        saveTimerRef.current = null
        return
      }

      void StudioShotDetailsService.updateShotDetailApiV1StudioShotDetailsShotIdPatch({
        shotId: selectedShotId,
        requestBody: patch as any,
      })
        .then((r: any) => {
          if (r.data) {
            setShotDetail(r.data)
            lastSavedDetailRef.current = r.data
            if (r.data.duration != null) {
              setShotDurations((m) => ({ ...m, [selectedShotId]: r.data?.duration ?? 0 }))
            }
          }
        })
        .catch(() => {
          message.error('自动保存失败')
        })
        .finally(() => {
          setSaving(false)
          saveTimerRef.current = null
        })
    }, 1000)
    return () => {
      if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current)
      saveTimerRef.current = null
    }
  }, [selectedShotId, shotDetail])

  // 播放器：同步时间与状态
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    const onPlay = () => setIsPlaying(true)
    const onPause = () => setIsPlaying(false)
    const onTimeUpdate = () => setVideoTime(v.currentTime || 0)
    const onLoaded = () => setVideoDuration(v.duration || 0)
    v.addEventListener('play', onPlay)
    v.addEventListener('pause', onPause)
    v.addEventListener('timeupdate', onTimeUpdate)
    v.addEventListener('loadedmetadata', onLoaded)
    return () => {
      v.removeEventListener('play', onPlay)
      v.removeEventListener('pause', onPause)
      v.removeEventListener('timeupdate', onTimeUpdate)
      v.removeEventListener('loadedmetadata', onLoaded)
    }
  }, [selectedShotId])

  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    v.playbackRate = playbackRate
  }, [playbackRate])

  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    v.loop = loopCurrent
  }, [loopCurrent])

  useEffect(() => {
    const v = videoRef.current
    if (!v || !currentPreviewVideoUrl) return
    v.load()
    void v.play().catch(() => {
      // 浏览器策略可能阻止自动播放，保留静默失败
    })
  }, [currentPreviewVideoUrl])

  // 快捷键：←/→ 切换分镜，Space 播放暂停，P/Ctrl+I 面板，H 隐藏，M 合并，Ctrl/Cmd+Enter 保存并生成
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target)) return
      const key = e.key.toLowerCase()

      if (key === 'p' || (key === 'i' && (e.ctrlKey || e.metaKey))) {
        e.preventDefault()
        setPrefs((p) => ({ ...p, inspectorOpen: !p.inspectorOpen }))
        return
      }

      if (key === ' ') {
        e.preventDefault()
        const v = videoRef.current
        if (!v) return
        if (v.paused) void v.play()
        else v.pause()
        return
      }

      if (key === 'arrowleft' || key === 'arrowright') {
        e.preventDefault()
        const visible = shots.filter((s) => !s.hidden)
        const idx = visible.findIndex((s) => s.id === selectedShotId)
        if (idx === -1) return
        const next = key === 'arrowleft' ? visible[idx - 1] : visible[idx + 1]
        if (next) setSelectedShotId(next.id)
        return
      }

      if ((e.ctrlKey || e.metaKey) && key === 'enter') {
        e.preventDefault()
        void generateFrameImageTask()
        return
      }

      if (key === 'h') {
        e.preventDefault()
        if (!selectedShotId) return
        toggleHiddenShots([selectedShotId])
        return
      }

      if (key === 'm') {
        e.preventDefault()
        if (selectedShotIds.length < 2) {
          message.info('请先多选至少 2 个分镜再合并')
          return
        }
        Modal.confirm({
          title: `合并 ${selectedShotIds.length} 个分镜？`,
          content: '将它们合并为一个新的分镜（Mock 行为）。',
          okText: '合并',
          cancelText: '取消',
          onOk: () => {
            message.success('已合并（Mock）')
          },
        })
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedShotId, selectedShotIds.length, shots, setPrefs])

  const statusTag = (status: ShotStatus | undefined) => {
    const s = status ?? 'pending'
    const map = { pending: 'default', generating: 'processing', ready: 'success' } as const
    const text = { pending: '待生成', generating: '生成中', ready: '已就绪' } as const
    return <Tag color={map[s]}>{text[s]}</Tag>
  }

  const statusDotClass = (status: ShotStatus | undefined) => {
    if (status === 'ready') return 'cs-ready'
    if (status === 'generating') return 'cs-generating'
    return 'cs-pending'
  }

  const chapterTitle = useMemo(() => {
    if (!chapter) return '章节拍摄工作台'
    return `第${chapter.index}章 · ${chapter.title.replace(/^第\d+[集章：:\s]*/g, '').trim() || chapter.title}`
  }, [chapter])

  const filteredShots = useMemo(() => {
    const list = shots.slice().sort((a, b) => a.index - b.index)
    switch (filter) {
      case 'pending':
        return list.filter((s) => !s.hidden && s.status !== 'ready')
      case 'ready':
        return list.filter((s) => !s.hidden && s.status === 'ready')
      case 'hidden':
        return list.filter((s) => Boolean(s.hidden))
      case 'problem':
        return list.filter((s) => !s.hidden && Boolean(s.hasProblem))
      default:
        return list
    }
  }, [filter, shots])

  const multiToolbarVisible = selectedShotIds.length > 1

  const handleSelectShot = (shotId: string, indexInFiltered: number, e: React.MouseEvent) => {
    setSelectedShotId(shotId)
    const isRange = e.shiftKey && lastSelectedIndexRef.current >= 0
    const isToggle = e.ctrlKey || e.metaKey

    if (isRange) {
      const start = Math.min(lastSelectedIndexRef.current, indexInFiltered)
      const end = Math.max(lastSelectedIndexRef.current, indexInFiltered)
      const rangeIds = filteredShots.slice(start, end + 1).map((s) => s.id)
      setSelectedShotIds(Array.from(new Set([...selectedShotIds, ...rangeIds])))
      return
    }

    if (isToggle) {
      setSelectedShotIds((prev) => (prev.includes(shotId) ? prev.filter((id) => id !== shotId) : [...prev, shotId]))
      lastSelectedIndexRef.current = indexInFiltered
      return
    }

    setSelectedShotIds([shotId])
    lastSelectedIndexRef.current = indexInFiltered
  }

  const matchesFilter = (s: StudioShot, f: ShotFilter) => {
    switch (f) {
      case 'pending':
        return !s.hidden && s.status !== 'ready'
      case 'ready':
        return !s.hidden && s.status === 'ready'
      case 'hidden':
        return Boolean(s.hidden)
      case 'problem':
        return !s.hidden && Boolean(s.hasProblem)
      default:
        return true
    }
  }

  const reorderWithinFilter = (sourceId: string, destId: string) => {
    if (sourceId === destId) return
    setShots((prev) => {
      const ordered = prev.slice().sort((a, b) => a.index - b.index)
      const subset = ordered.filter((s) => matchesFilter(s, filter))
      const sourceIndex = subset.findIndex((s) => s.id === sourceId)
      const destIndex = subset.findIndex((s) => s.id === destId)
      if (sourceIndex === -1 || destIndex === -1) return prev
      const movedSubset = reorder(subset, sourceIndex, destIndex)
      const movedQueue = [...movedSubset]
      const replaced = ordered.map((s) => (matchesFilter(s, filter) ? (movedQueue.shift() as StudioShot) : s))
      const next = replaced.map((s, idx) => ({ ...s, index: idx + 1 }))

      // 后台同步排序（不阻塞 UI）
      const beforeMap = new Map(prev.map((s) => [s.id, s.index]))
      void (async () => {
        try {
          const changed = next.filter((s) => beforeMap.get(s.id) !== s.index)
          await Promise.all(
            changed.map((s) =>
              StudioShotsService.updateShotApiV1StudioShotsShotIdPatch({
                shotId: s.id,
                requestBody: { index: s.index },
              }),
            ),
          )
        } catch {
          message.error('同步排序失败')
        }
      })()

      return next
    })
  }

  const beginResize = (type: 'left' | 'right', e: React.PointerEvent) => {
    if (!containerRef.current) return
    const startX = e.clientX
    dragStateRef.current = {
      type,
      startX,
      startLeft: prefs.leftWidth,
      startRight: prefs.rightWidth,
    }
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    setIsResizing(true)
  }

  const onResizeMove = (e: React.PointerEvent) => {
    const st = dragStateRef.current
    if (!st) return
    const dx = e.clientX - st.startX
    const minLeft = 240
    const maxLeft = 360
    const minRight = 360
    const maxRight = 720
    if (st.type === 'left') {
      pendingResizeRef.current = { leftWidth: clamp(st.startLeft + dx, minLeft, maxLeft) }
    } else {
      // right：推挤/覆盖都复用 width 偏好
      pendingResizeRef.current = { rightWidth: clamp(st.startRight - dx, minRight, maxRight) }
    }

    if (resizeRafRef.current) return
    resizeRafRef.current = window.requestAnimationFrame(() => {
      const pending = pendingResizeRef.current
      pendingResizeRef.current = null
      resizeRafRef.current = null
      if (!pending) return
      setPrefs((p) => ({
        ...p,
        ...(typeof pending.leftWidth === 'number' ? { leftWidth: pending.leftWidth } : null),
        ...(typeof pending.rightWidth === 'number' ? { rightWidth: pending.rightWidth } : null),
      }))
    })
  }

  const endResize = () => {
    dragStateRef.current = null
    pendingResizeRef.current = null
    if (resizeRafRef.current) {
      window.cancelAnimationFrame(resizeRafRef.current)
      resizeRafRef.current = null
    }
    setIsResizing(false)
  }

  const shotContextMenu = (shot: StudioShot) => ([
    {
      key: 'copy',
      icon: <LinkOutlined />,
      label: '复制分镜',
      onClick: () => message.success('已复制（Mock）'),
    },
    {
      key: 'insert_after',
      icon: <VideoCameraAddOutlined />,
      label: '在后插入新分镜',
      onClick: () => message.success('已插入（Mock）'),
    },
    {
      key: 'transition',
      icon: <ScissorOutlined />,
      label: '设为转场点',
      onClick: () => message.success('已设置（Mock）'),
    },
    { type: 'divider' as const },
    {
      key: 'toggle_hide',
      icon: shot.hidden ? <EyeOutlined /> : <EyeInvisibleOutlined />,
      label: shot.hidden ? '取消隐藏' : '隐藏',
      onClick: () => toggleHiddenShots([shot.id]),
    },
    {
      key: 'delete',
      icon: <DeleteOutlined />,
      danger: true,
      label: '删除',
      onClick: () =>
        Modal.confirm({
          title: '删除分镜？',
          content: '此操作不可撤销。',
          okText: '删除',
          okButtonProps: { danger: true },
          cancelText: '取消',
          onOk: async () => {
            try {
              await StudioShotsService.deleteShotApiV1StudioShotsShotIdDelete({ shotId: shot.id })
              await loadShots()
              message.success('已删除')
            } catch {
              message.error('删除失败')
            }
          },
        }),
    },
  ])

  const batchMenuItems = [
    {
      key: 'merge',
      icon: <MergeCellsOutlined />,
      label: '合并',
      disabled: selectedShotIds.length < 2,
      onClick: () => {
        if (selectedShotIds.length < 2) return
        Modal.confirm({
          title: `合并 ${selectedShotIds.length} 个分镜？`,
          okText: '合并',
          cancelText: '取消',
          onOk: () => message.success('已合并（Mock）'),
        })
      },
    },
    {
      key: 'hide',
      icon: <EyeInvisibleOutlined />,
      label: '隐藏',
      onClick: () => toggleHiddenShots(selectedShotIds),
    },
    {
      key: 'delete',
      icon: <DeleteOutlined />,
      danger: true,
      label: '删除',
      onClick: () =>
        Modal.confirm({
          title: `删除 ${selectedShotIds.length} 个分镜？`,
          okText: '删除',
          okButtonProps: { danger: true },
          cancelText: '取消',
          onOk: async () => {
            try {
              await Promise.all(selectedShotIds.map((id) => StudioShotsService.deleteShotApiV1StudioShotsShotIdDelete({ shotId: id })))
              await loadShots()
              message.success('已删除')
            } catch {
              message.error('删除失败')
            }
          },
        }),
    },
    { type: 'divider' as const },
    {
      key: 'generate',
      icon: <ThunderboltOutlined />,
      label: '批量生成',
      onClick: () => {
        if (selectedShotIds.length === 0) return
        Modal.confirm({
          title: `批量生成 ${selectedShotIds.length} 个分镜？`,
          okText: '开始',
          cancelText: '取消',
          onOk: async () => {
            setGenerating(true)
            try {
              for (const id of selectedShotIds) {
                const framesRes = await StudioShotFrameImagesService.listShotFrameImagesApiV1StudioShotFrameImagesGet({
                  shotDetailId: id,
                  order: null,
                  isDesc: false,
                  page: 1,
                  pageSize: 100,
                })
                const frames = framesRes.data?.items ?? []
                const target = frames.find((x) => x.frame_type === 'key') ?? frames[0]
                if (!target) continue

                const detailRes: any = await StudioShotDetailsService.getShotDetailApiV1StudioShotDetailsShotIdGet({ shotId: id })
                const d = detailRes?.data as any
                const prompt =
                  (target.frame_type === 'first'
                    ? d?.first_frame_prompt
                    : target.frame_type === 'last'
                      ? d?.last_frame_prompt
                      : d?.key_frame_prompt) ?? ''
                if (!String(prompt || '').trim()) continue

                const linked = await StudioShotsService.listShotLinkedAssetsApiV1StudioShotsShotIdLinkedAssetsGet({
                  shotId: id,
                  page: 1,
                  pageSize: 100,
                })
                const items = (linked.data?.items ?? []) as any[]
                const extractFileId = (thumbnail?: string | null): string | null => {
                  const v = (thumbnail || '').trim()
                  if (!v) return null
                  if (!v.includes('/') && !v.includes(':')) return v
                  try {
                    const url = new URL(v, typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
                    const m = url.pathname.match(/\/api\/v1\/studio\/files\/([^/]+)\/download\/?$/)
                    if (m?.[1]) return decodeURIComponent(m[1])
                  } catch {
                    // ignore
                  }
                  return null
                }
                const imagesPayload = items
                  .map((x) => {
                    const fileId = typeof x?.file_id === 'string' && x.file_id.trim() ? x.file_id.trim() : extractFileId(x?.thumbnail)
                    return fileId
                      ? {
                          type: x?.type as any,
                          id: String(x?.id ?? ''),
                          name: String(x?.name ?? x?.id ?? ''),
                          file_id: fileId,
                        }
                      : null
                  })
                  .filter(Boolean)
                await StudioImageTasksService.createShotFrameImageGenerationTaskApiV1StudioImageTasksShotShotIdFrameImageTasksPost({
                  shotId: id,
                  requestBody: { frame_type: target.frame_type as any, model_id: null, prompt, images: imagesPayload } as any,
                })
              }
              message.success('已创建批量生成任务')
            } catch {
              message.error('批量生成失败')
            } finally {
              setGenerating(false)
            }
          },
        })
      },
    },
  ]

  const toolbarSettingsItems = [
    {
      key: 'mode',
      icon: <AppstoreOutlined />,
      label: (
        <div className="flex items-center justify-between gap-3">
          <span>属性面板模式</span>
          <Select
            size="small"
            value={prefs.inspectorMode}
            style={{ width: 120 }}
            onChange={(v) => setPrefs((p) => ({ ...p, inspectorMode: v }))}
            options={[
              { value: 'push', label: '推挤模式' },
              { value: 'overlay', label: '覆盖模式' },
            ]}
          />
        </div>
      ),
    },
    {
      key: 'autoOpen',
      icon: <SettingOutlined />,
      label: (
        <div className="flex items-center justify-between gap-3">
          <span>选中分镜自动展开</span>
          <Switch
            size="small"
            checked={prefs.autoOpenInspector}
            onChange={(v) => setPrefs((p) => ({ ...p, autoOpenInspector: v }))}
          />
        </div>
      ),
    },
  ]

  const subtitleLines = useMemo(() => {
    if (!selectedShot || dialogLines.length === 0) return []
    const dur = Math.max(1, shotDetail?.duration ?? shotDurations[selectedShot.id] ?? 1)
    const per = dur / dialogLines.length
    return dialogLines.map((d, i) => ({
      key: `${selectedShot.id}-${d.id}`,
      role: d.speaker_character_id ?? '—',
      text: d.text,
      start: i * per,
      end: (i + 1) * per,
    }))
  }, [dialogLines, selectedShot, shotDetail?.duration, shotDurations])

  const activeSubtitleIndex = useMemo(() => {
    if (!selectedShot || subtitleLines.length === 0) return -1
    const t = videoTime
    return subtitleLines.findIndex((l) => t >= l.start && t < l.end)
  }, [selectedShot, subtitleLines, videoTime])

  return (
    <div className={['cs-studio w-full h-full min-h-0 flex flex-col', isResizing ? 'cs-resizing' : ''].join(' ')} ref={containerRef}>
      {/* 顶部工具栏（常驻） */}
      <div
        className="cs-topbar flex items-center gap-4 px-4 py-3"
        style={{
          flexShrink: 0,
        }}
      >
        <div className="flex items-center gap-2 min-w-0">
          {projectId && (
            <Link
              to={`/projects/${projectId}?tab=chapters`}
              className="text-sm text-gray-600 hover:text-blue-600 flex items-center gap-1 shrink-0"
            >
              <ArrowLeftOutlined /> 返回
            </Link>
          )}
          <Divider type="vertical" />
          <div className="min-w-0">
            <div className="font-medium text-gray-900 truncate">{chapterTitle}</div>
            <div className="text-xs text-gray-500">
              {saving ? (
                <span className="inline-flex items-center gap-1">
                  <ClockCircleOutlined /> 自动保存中…
                </span>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <CheckCircleOutlined /> 已保存
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex-1 min-w-0 flex items-center justify-center">
          <Space size="middle" wrap>
            <Button
              size="small"
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={() => message.success('智能精简完成（Mock）')}
            >
              智能精简
            </Button>
            <Button
              size="small"
              icon={<ThunderboltOutlined />}
              onClick={() => message.success('已提取角色/场景/道具/分镜建议（Mock）')}
            >
              智能提取全部
            </Button>
            <Dropdown menu={{ items: batchMenuItems }} disabled={selectedShotIds.length === 0}>
              <Button size="small">
                批量操作 <DownOutlined />
              </Button>
            </Dropdown>
            <Button size="small" type="primary" icon={<SaveOutlined />} onClick={() => message.success('已保存草稿（Mock）')}>
              保存草稿
            </Button>
            <Button
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => message.info('预览整章（Mock：连续播放非隐藏分镜）')}
            >
              预览整章
            </Button>
            <Button
              size="small"
              icon={<ExportOutlined />}
              onClick={() => setExportModalOpen(true)}
            >
              导出分镜表
            </Button>
          </Space>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Dropdown menu={{ items: toolbarSettingsItems }} trigger={['click']}>
            <Tooltip title="工作台设置">
              <Button size="small" icon={<SettingOutlined />} />
            </Tooltip>
          </Dropdown>
          <Tooltip title={prefs.inspectorOpen ? '收起属性面板（P / Ctrl/Cmd+I）' : '展开属性面板（P / Ctrl/Cmd+I）'}>
            <Button
              size="small"
              icon={prefs.inspectorOpen ? <DoubleRightOutlined /> : <DoubleLeftOutlined />}
              onClick={() => setPrefs((p) => ({ ...p, inspectorOpen: !p.inspectorOpen }))}
            />
          </Tooltip>
        </div>
      </div>

      {/* 三栏动态布局 */}
      <Layout
        className="flex-1 min-h-0"
        style={{
          background: 'transparent',
          position: 'relative',
          overflow: 'hidden',
        }}
        onPointerMove={onResizeMove}
        onPointerUp={endResize}
        onPointerCancel={endResize}
      >
        {/* 左侧：分镜列表 */}
        <Sider
          width={prefs.leftWidth}
          collapsedWidth={0}
          className="cs-left flex flex-col"
          style={{
            overflow: 'hidden',
          }}
        >
          <div className="cs-group m-3 mb-2 flex flex-col gap-2 min-w-0">
            <div className="cs-group-title mb-0 flex items-center gap-2 shrink-0">
              <FileTextOutlined /> 分镜列表
            </div>
            <div className="overflow-x-auto min-w-0 -mx-1 px-1">
              <Segmented
                size="small"
                value={filter}
                onChange={(v) => setFilter(v as ShotFilter)}
                options={[
                  { label: '全部', value: 'all' },
                  { label: '未完成', value: 'pending' },
                  { label: '已生成', value: 'ready' },
                  { label: '隐藏', value: 'hidden' },
                  { label: '有问题', value: 'problem' },
                ]}
              />
            </div>
          </div>

          {multiToolbarVisible && (
            <div className="cs-group m-3 mt-0 mb-2">
              <div className="cs-group-title mb-2 flex items-center gap-2">
                <AppstoreOutlined /> 批量操作
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-gray-600">已选 {selectedShotIds.length} 项</span>
              <Button size="small" icon={<MergeCellsOutlined />} disabled={selectedShotIds.length < 2} onClick={() => batchMenuItems[0].onClick?.()}>
                合并
              </Button>
              <Button size="small" icon={<EyeInvisibleOutlined />} onClick={() => batchMenuItems[1].onClick?.()}>
                隐藏
              </Button>
              <Button size="small" icon={<SoundOutlined />} onClick={() => message.success('已批量关闭配乐/对白（Mock）')}>
                关闭配乐/对白
              </Button>
              <Button size="small" icon={<ThunderboltOutlined />} loading={generating} onClick={() => batchMenuItems[4].onClick?.()}>
                批量生成
              </Button>
              </div>
            </div>
          )}

          <div className="flex-1 min-h-0 overflow-auto px-3 pb-3">
            {loadingShots ? (
              <div className="text-gray-500 text-center py-4">加载中...</div>
            ) : (
              <div>
                {filteredShots.map((s, i) => {
                  const isActive = selectedShotId === s.id
                  const isSelected = selectedShotIds.includes(s.id)
                  const isDragging = draggingShotId === s.id
                  const isDragOver = dragOverShotId === s.id && draggingShotId && draggingShotId !== s.id
                  return (
                    <div
                      key={s.id}
                      draggable
                      onDragStart={(e) => {
                        setDraggingShotId(s.id)
                        setDragOverShotId(null)
                        e.dataTransfer.effectAllowed = 'move'
                        e.dataTransfer.setData('text/plain', s.id)
                      }}
                      onDragEnter={() => {
                        if (!draggingShotId || draggingShotId === s.id) return
                        setDragOverShotId(s.id)
                      }}
                      onDragOver={(e) => {
                        e.preventDefault()
                        e.dataTransfer.dropEffect = 'move'
                      }}
                      onDrop={(e) => {
                        e.preventDefault()
                        const sourceId = e.dataTransfer.getData('text/plain') || draggingShotId
                        if (!sourceId) return
                        reorderWithinFilter(sourceId, s.id)
                        setDraggingShotId(null)
                        setDragOverShotId(null)
                      }}
                      onDragEnd={() => {
                        setDraggingShotId(null)
                        setDragOverShotId(null)
                      }}
                      style={{
                        opacity: isDragging ? 0.92 : 1,
                        outline: isDragOver ? '2px dashed var(--ant-color-primary)' : 'none',
                        borderRadius: 8,
                      }}
                    >
                      <Dropdown menu={{ items: shotContextMenu(s) }} trigger={['contextMenu']}>
                        <Card
                          size="small"
                          className={[
                            'cs-shot-item mb-2 cursor-pointer transition-colors',
                            isSelected ? 'cs-shot-selected' : '',
                            isActive ? 'cs-shot-active' : '',
                          ].filter(Boolean).join(' ')}
                          style={{
                            opacity: s.hidden ? 0.55 : 1,
                          }}
                          onClick={(e) => handleSelectShot(s.id, i, e)}
                          onDoubleClick={() => {
                            setEditingTitleId(s.id)
                            setEditingTitleValue(s.title)
                          }}
                        >
                          <div className="flex gap-2">
                            <div className="w-16 h-10 rounded bg-gray-200 flex-shrink-0 flex items-center justify-center text-gray-400 text-xs overflow-hidden">
                              <span>16:9</span>
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className={`cs-dot ${statusDotClass(s.status)}`} />
                                <span className="text-xs text-gray-500 shrink-0">
                                  {String(s.index).padStart(2, '0')}
                                </span>
                                {editingTitleId === s.id ? (
                                  <Input
                                    size="small"
                                    value={editingTitleValue}
                                    autoFocus
                                    onChange={(ev) => setEditingTitleValue(ev.target.value)}
                                    onBlur={() => {
                                      const nextTitle = editingTitleValue.trim()
                                      setShots((prev) => prev.map((x) => (x.id === s.id ? { ...x, title: nextTitle || x.title } : x)))
                                      if (nextTitle && nextTitle !== s.title) {
                                        void StudioShotsService.updateShotApiV1StudioShotsShotIdPatch({
                                          shotId: s.id,
                                          requestBody: { title: nextTitle },
                                        }).catch(() => message.error('保存标题失败'))
                                      }
                                      setEditingTitleId(null)
                                    }}
                                    onKeyDown={(ev) => {
                                      if (ev.key === 'Enter') {
                                        (ev.currentTarget as HTMLInputElement).blur()
                                      }
                                      if (ev.key === 'Escape') {
                                        setEditingTitleId(null)
                                      }
                                    }}
                                  />
                                ) : (
                                  <div className="font-medium text-sm truncate" title="双击编辑标题">
                                    {s.title}
                                  </div>
                                )}
                              </div>
                              <div className="text-xs text-gray-500 mt-1 truncate">
                                {shotDetail?.movement ? `${CAMERA_MOVEMENT_OPTIONS.find((x) => x.value === shotDetail.movement)?.label ?? shotDetail.movement} · ` : ''}
                                {((shotDurations[s.id] ?? shotDetail?.duration ?? 0) || 0).toFixed(1)}s
                              </div>
                              <div className="mt-1 flex flex-wrap gap-1 items-center">
                                {s.hasSpeech && <Tag icon={<FileTextOutlined />} className="m-0" color="default">说话</Tag>}
                                {s.hasMusic && <Tag icon={<SoundOutlined />} className="m-0" color="default">音乐</Tag>}
                                {statusTag(s.status)}
                                {s.hidden && <Tag icon={<EyeInvisibleOutlined />} className="m-0">隐藏</Tag>}
                                {s.hasProblem && <Tag color="error" className="m-0">有问题</Tag>}
                              </div>
                            </div>
                          </div>
                        </Card>
                      </Dropdown>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </Sider>

        {/* 左侧拖拽条 */}
        <div
          role="separator"
          className="cs-sep h-full"
          style={{
            width: 10,
            cursor: 'col-resize',
            background: 'transparent',
            flexShrink: 0,
          }}
          onPointerDown={(e) => beginResize('left', e)}
          title="拖拽调整左侧宽度"
        />

        {/* 中央：主预览区 */}
        <Content className="cs-main min-w-0 min-h-0 flex flex-col" style={{ padding: 16, position: 'relative', overflow: 'hidden' }}>
          <Card
            title={
              <div className="flex items-center gap-3 min-w-0">
                <span className="font-medium">主预览区</span>
                {selectedShot && (
                  <span className="text-xs text-gray-500 truncate">
                    当前分镜：{String(selectedShot.index).padStart(2, '0')} · {selectedShot.title}
                  </span>
                )}
              </div>
            }
            extra={
              <Space size="small">
                {showPreviewMinimizeButton && (
                  <Tooltip title="最小化预览（占位）">
                    <Button size="small" icon={<DoubleRightOutlined />} onClick={() => message.info('最小化预览（Mock）')} />
                  </Tooltip>
                )}
                <Tooltip title="截取当前帧（Mock）">
                  <Button size="small" icon={<ScissorOutlined />} onClick={() => message.success('已截取当前帧（Mock）')} />
                </Tooltip>
                <Tooltip title={currentPreviewVideoFileId ? '下载当前预览视频' : '暂无可下载视频'}>
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    disabled={!currentPreviewVideoFileId || !currentPreviewVideoUrl}
                    onClick={() => {
                      if (!currentPreviewVideoUrl) return
                      window.open(currentPreviewVideoUrl, '_blank', 'noopener,noreferrer')
                    }}
                  />
                </Tooltip>
              </Space>
            }
            className="cs-preview-card flex-1 min-h-0"
            bodyStyle={{ height: '100%', minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', gap: 12 }}
          >
            <div className="flex items-center justify-between gap-2">
              {showPreviewFrameSegmented ? (
                <Segmented
                  size="small"
                  value={frameTab}
                  onChange={(v) => setFrameTab(v as typeof frameTab)}
                  options={[
                    { label: '首帧', value: 'head' },
                    { label: '关键帧列表', value: 'keyframes' },
                    { label: '尾帧', value: 'tail' },
                    { label: '参考对比', value: 'compare' },
                  ]}
                />
              ) : (
                <div />
              )}
              <Space size="small">
                <Select
                  size="small"
                  value={playbackRate}
                  style={{ width: 86 }}
                  onChange={(v) => setPlaybackRate(v)}
                  options={[0.5, 1, 1.25, 1.5, 2].map((v) => ({ label: `${v}x`, value: v }))}
                />
                <Tooltip title="循环当前分镜">
                  <Switch size="small" checked={loopCurrent} onChange={setLoopCurrent} />
                </Tooltip>
                <Space size={4} className="max-w-[320px]">
                  <Radio.Group
                    size="small"
                    buttonStyle="solid"
                    disabled={!currentFrameFileId || frameFileTagsLoading}
                    value={currentFrameFileTags.includes(FRAME_FILE_TAG_ADOPT) ? FRAME_FILE_TAG_ADOPT : currentFrameFileTags.includes(FRAME_FILE_TAG_ABANDON) ? FRAME_FILE_TAG_ABANDON : ''}
                    onChange={(e) => {
                      const v = String(e?.target?.value ?? '')
                      const base = currentFrameFileTags.filter((t) => t !== FRAME_FILE_TAG_ADOPT && t !== FRAME_FILE_TAG_ABANDON)
                      if (!v) void updateCurrentFrameFileTags(base)
                      else void updateCurrentFrameFileTags([v, ...base])
                    }}
                  >
                    <Radio.Button value={FRAME_FILE_TAG_ADOPT}>采用</Radio.Button>
                    <Radio.Button value={FRAME_FILE_TAG_ABANDON}>废弃</Radio.Button>
                  </Radio.Group>
                  <Select
                    mode="tags"
                    size="small"
                    style={{ minWidth: 160, maxWidth: 220 }}
                    placeholder="自定义标签"
                    disabled={!currentFrameFileId || frameFileTagsLoading}
                    loading={frameFileTagsLoading}
                    value={currentFrameFileTags.filter((t) => t !== FRAME_FILE_TAG_ADOPT && t !== FRAME_FILE_TAG_ABANDON)}
                    onChange={(vals) => {
                      const base = Array.isArray(vals) ? (vals as any[]).map((v) => String(v)) : []
                      const keep =
                        currentFrameFileTags.find((t) => t === FRAME_FILE_TAG_ADOPT || t === FRAME_FILE_TAG_ABANDON) ?? null
                      void updateCurrentFrameFileTags(keep ? [keep, ...base] : base)
                    }}
                  />
                </Space>
                <Tooltip title="当前镜头数据">
                  <Tag className="m-0">
                    帧图 {frameImages.length} · 关联 {sceneLinks.length + actorImageLinks.length + propLinks.length + costumeLinks.length}
                  </Tag>
                </Tooltip>
              </Space>
            </div>

            <div className="flex-1 min-h-0 overflow-auto flex flex-col gap-8 pr-1">
              <div className="relative">
                <div className="cs-player-shell">
                  <div className="aspect-video bg-black rounded overflow-hidden flex items-center justify-center">
                  {/* Mock：没有真实视频源时仍可展示播放器结构 */}
                  <video
                    ref={videoRef}
                    className="w-full h-full object-contain"
                    controls={false}
                    muted
                    playsInline
                    preload="metadata"
                    src={currentPreviewVideoUrl || undefined}
                  />
                  {!selectedShot && (
                    <div className="absolute inset-0 flex items-center justify-center text-gray-400">
                      请选择分镜
                    </div>
                  )}
                  {selectedShot && !currentPreviewVideoUrl && selectedShot.status !== 'ready' && (
                    <div className="absolute inset-0 flex items-center justify-center">
                      <Badge
                        status={selectedShot.status === 'generating' ? 'processing' : 'default'}
                        text={selectedShot.status === 'generating' ? '生成中…' : '未生成'}
                      />
                    </div>
                  )}
                  </div>
                </div>

                {/* 播放控制条 */}
                <div className="mt-2 flex items-center gap-2">
                  <Button
                    size="small"
                    icon={<CaretLeftOutlined />}
                    onClick={() => message.info('帧退（Mock）')}
                  />
                  <Button
                    size="small"
                    type="primary"
                    icon={isPlaying ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                    onClick={() => {
                      const v = videoRef.current
                      if (!v) return
                      if (v.paused) void v.play()
                      else v.pause()
                    }}
                  >
                    {isPlaying ? '暂停' : '播放'}
                  </Button>
                  <Button
                    size="small"
                    icon={<CaretRightOutlined />}
                    onClick={() => message.info('帧进（Mock）')}
                  />
                  <div className="flex-1 min-w-0">
                    <Slider
                      tooltip={{ formatter: null }}
                      min={0}
                      max={Math.max(1, videoDuration || shotDetail?.duration || (selectedShotId ? shotDurations[selectedShotId] : 0) || 1)}
                      value={videoTime}
                      onChange={(v) => {
                        const vv = videoRef.current
                        if (!vv) return
                        vv.currentTime = Number(v)
                        setVideoTime(Number(v))
                      }}
                    />
                  </div>
                  <div className="text-xs text-gray-400 w-[110px] text-right">
                    {videoTime.toFixed(1)} / {Math.max(videoDuration || 0, shotDetail?.duration || (selectedShotId ? shotDurations[selectedShotId] : 0) || 0).toFixed(1)}s
                  </div>
                </div>

                {/* 对白字幕条 */}
                <div className="cs-subtitle mt-2 px-3 py-2">
                  {subtitleLines.length === 0 ? (
                    <div className="text-sm opacity-80">暂无对白字幕</div>
                  ) : (
                    <div className="flex flex-col gap-1">
                      {subtitleLines.map((l, idx) => {
                        const active = idx === activeSubtitleIndex
                        return (
                          <div
                            key={l.key}
                            className="cs-sub-line text-sm cursor-pointer"
                            style={{ opacity: active ? 1 : 0.6, fontWeight: active ? 600 : 400 }}
                            onClick={() => {
                              const v = videoRef.current
                              if (!v) return
                              v.currentTime = l.start
                              setVideoTime(l.start)
                            }}
                          >
                            <span style={{ opacity: 0.9 }}>{l.role}：</span>
                            <span>{l.text}</span>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* 章节级时间轴（可折叠，固定在底部不参与滚动） */}
            {showChapterTimeline && (
              <div
                className="rounded border border-solid border-gray-200 flex-shrink-0 min-h-0 flex flex-col"
                style={{ background: 'var(--ant-color-bg-container)' }}
              >
                <div className="px-3 py-2 flex items-center justify-between flex-shrink-0">
                  <div className="text-sm font-medium">章节时间轴</div>
                  <Button
                    size="small"
                    type="text"
                    onClick={() => setPrefs((p) => ({ ...p, timelineCollapsed: !p.timelineCollapsed }))}
                  >
                    {prefs.timelineCollapsed ? '展开' : '折叠'}
                  </Button>
                </div>
                {!prefs.timelineCollapsed && (
                  <div className="px-3 pb-3 flex-shrink-0 overflow-hidden">
                    <div className="flex items-center gap-2 overflow-x-auto py-1 min-h-[32px]">
                      {shots
                        .slice()
                        .sort((a, b) => a.index - b.index)
                        .filter((s) => !s.hidden)
                        .map((s) => {
                          const active = s.id === selectedShotId
                          return (
                            <div
                              key={s.id}
                              className="shrink-0 cursor-pointer rounded"
                              style={{
                                width: clamp(18 + ((shotDurations[s.id] ?? 1) || 1) * 6, 24, 96),
                                height: 14,
                                background:
                                  s.status === 'ready'
                                    ? 'rgba(34,197,94,0.45)'
                                    : s.status === 'generating'
                                      ? 'rgba(59,130,246,0.45)'
                                      : 'rgba(156,163,175,0.45)',
                                outline: active ? '2px solid var(--ant-color-primary)' : '1px solid rgba(0,0,0,0.06)',
                              }}
                              title={`${String(s.index).padStart(2, '0')} · ${s.title}`}
                              onClick={() => setSelectedShotId(s.id)}
                            />
                          )
                        })}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      点击条块跳转分镜；隐藏分镜不参与预览
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>
        </Content>

        {/* 右侧：属性面板（推挤 / 覆盖） */}
        {prefs.inspectorMode === 'push' ? (
          <>
            {/* 右侧拖拽条（推挤模式） */}
            {prefs.inspectorOpen && (
              <div
                role="separator"
                className="cs-sep cs-sep-strong h-full"
                style={{
                  width: 10,
                  cursor: 'col-resize',
                  background: 'transparent',
                  flexShrink: 0,
                }}
                onPointerDown={(e) => beginResize('right', e)}
                title="拖拽调整属性面板宽度"
              />
            )}
            <Sider
              width={prefs.inspectorOpen ? prefs.rightWidth : 0}
              collapsedWidth={0}
              collapsed={!prefs.inspectorOpen}
              className="cs-right"
              style={{
                overflow: 'hidden',
              }}
            >
              <Inspector
                projectId={projectId}
                loadingDetail={loadingDetail}
                shotDetail={shotDetail}
                dialogLines={dialogLines}
                frameImages={frameImages}
                sceneLinks={sceneLinks}
                propLinks={propLinks}
                costumeLinks={costumeLinks}
                shotCharacterLinks={shotCharacterLinks}
                cameraUpdating={cameraUpdating}
                promptAssetsUpdating={promptAssetsUpdating}
                onAddDialogLine={addDialogLine}
                onDeleteDialogLine={deleteDialogLine}
                onUpdatePromptScene={updatePromptScene}
                onUpdatePromptActors={updatePromptActors}
                onUpdatePromptProps={updatePromptProps}
                onUpdatePromptCostumes={updatePromptCostumes}
                selectedShot={selectedShot}
                onUpdateShotTitle={updateShotTitleInOps}
                onUpdateShotScriptExcerpt={updateShotScriptExcerptInOps}
                onDeleteShotOps={deleteShotFromOps}
                onPatchShotDetail={patchShotDetailLocal}
                onPatchShotDetailImmediate={patchShotDetailImmediate}
                onSelectPreviewVideo={setPreviewVideoFileId}
                onClose={() => setPrefs((p) => ({ ...p, inspectorOpen: false }))}
              />
            </Sider>

            {!prefs.inspectorOpen && (
              <div
                className="cs-right-strip"
                onClick={() => setPrefs((p) => ({ ...p, inspectorOpen: true }))}
                title="展开属性面板（P / Ctrl/Cmd+I）"
              >
                <span>属性</span>
              </div>
            )}
          </>
        ) : (
          <>
            {/* 覆盖模式：右侧抽屉覆盖中央 */}
            {prefs.inspectorOpen && (
              <div
                className="absolute top-0 right-0 h-full"
                style={{
                  width: prefs.rightWidth,
                  background: '#f9fafc',
                  borderLeft: '2px solid #cbd5e1',
                  zIndex: 20,
                  boxShadow: '-4px 0 12px rgba(0,0,0,0.06)',
                  display: 'flex',
                  flexDirection: 'row',
                }}
              >
                <div
                  role="separator"
                  className="cs-sep cs-sep-strong"
                  style={{ width: 10, flexShrink: 0 }}
                  onPointerDown={(e) => beginResize('right', e)}
                  title="拖拽调整覆盖宽度"
                />
                <div className="flex-1 min-w-0 overflow-hidden">
                  <Inspector
                    projectId={projectId}
                    loadingDetail={loadingDetail}
                    shotDetail={shotDetail}
                    dialogLines={dialogLines}
                    frameImages={frameImages}
                    sceneLinks={sceneLinks}
                    propLinks={propLinks}
                    costumeLinks={costumeLinks}
                    shotCharacterLinks={shotCharacterLinks}
                    cameraUpdating={cameraUpdating}
                    promptAssetsUpdating={promptAssetsUpdating}
                    onAddDialogLine={addDialogLine}
                    onDeleteDialogLine={deleteDialogLine}
                    onUpdatePromptScene={updatePromptScene}
                    onUpdatePromptActors={updatePromptActors}
                    onUpdatePromptProps={updatePromptProps}
                    onUpdatePromptCostumes={updatePromptCostumes}
                    selectedShot={selectedShot}
                    onUpdateShotTitle={updateShotTitleInOps}
                    onUpdateShotScriptExcerpt={updateShotScriptExcerptInOps}
                    onDeleteShotOps={deleteShotFromOps}
                    onPatchShotDetail={patchShotDetailLocal}
                    onPatchShotDetailImmediate={patchShotDetailImmediate}
                    onSelectPreviewVideo={setPreviewVideoFileId}
                    onClose={() => setPrefs((p) => ({ ...p, inspectorOpen: false }))}
                  />
                </div>
              </div>
            )}

            {/* 覆盖模式下，右侧边缘常驻开关 */}
            <Tooltip title={prefs.inspectorOpen ? '收起属性面板' : '展开属性面板'}>
              <Button
                size="small"
                className="absolute top-1/2 -translate-y-1/2"
                style={{ right: 4, zIndex: 30 }}
                icon={prefs.inspectorOpen ? <DoubleRightOutlined /> : <DoubleLeftOutlined />}
                onClick={() => setPrefs((p) => ({ ...p, inspectorOpen: !p.inspectorOpen }))}
              />
            </Tooltip>
          </>
        )}
      </Layout>

      {/* 导出弹窗 */}
      <Modal
        title="导出分镜表"
        open={exportModalOpen}
        onCancel={() => setExportModalOpen(false)}
        okText="导出"
        cancelText="取消"
        onOk={() => {
          setExportModalOpen(false)
          message.success(`已导出 ${exportFormat.toUpperCase()}（Mock）`)
        }}
      >
        <div className="space-y-3">
          <div className="text-sm text-gray-600">选择导出格式</div>
          <Radio.Group
            value={exportFormat}
            onChange={(e) => setExportFormat(e.target.value)}
            options={[
              { value: 'excel', label: <span className="inline-flex items-center gap-2"><FileExcelOutlined /> Excel</span> },
              { value: 'json', label: <span className="inline-flex items-center gap-2"><FileTextOutlined /> JSON</span> },
              { value: 'pdf', label: <span className="inline-flex items-center gap-2"><FilePdfOutlined /> PDF</span> },
            ]}
          />
          <div className="text-xs text-gray-500">将导出当前章节的分镜脚本与关键字段（Mock）。</div>
        </div>
      </Modal>
    </div>
  )
}

export default ChapterStudio

function Inspector(props: {
  projectId?: string
  loadingDetail: boolean
  shotDetail: ShotDetailRead | null
  dialogLines: ShotDialogLineRead[]
  frameImages: ShotFrameImageRead[]
  sceneLinks: ProjectSceneLinkRead[]
  propLinks: ProjectPropLinkRead[]
  costumeLinks: ProjectCostumeLinkRead[]
  shotCharacterLinks: ShotCharacterLinkRead[]
  cameraUpdating: boolean
  promptAssetsUpdating: boolean
  onAddDialogLine: (text: string) => Promise<void>
  onDeleteDialogLine: (lineId: number) => Promise<void>
  onUpdatePromptScene: (sceneId?: string) => Promise<void>
  onUpdatePromptActors: (actorIds: string[]) => Promise<void>
  onUpdatePromptProps: (propIds: string[]) => Promise<void>
  onUpdatePromptCostumes: (costumeIds: string[]) => Promise<void>
  selectedShot: StudioShot | null
  onUpdateShotTitle: (shotId: string, title: string) => Promise<void>
  onUpdateShotScriptExcerpt: (shotId: string, script_excerpt: string) => Promise<void>
  onDeleteShotOps: (shotId: string) => Promise<void>
  onClose: () => void
  onPatchShotDetail: (patch: Partial<ShotDetailRead>) => void
  onPatchShotDetailImmediate: (patch: Partial<ShotDetailRead>) => Promise<void>
  onSelectPreviewVideo: (fileId: string) => void
}) {
  const {
    projectId,
    loadingDetail,
    shotDetail,
    dialogLines,
    frameImages,
    sceneLinks,
    propLinks,
    costumeLinks,
    shotCharacterLinks,
    cameraUpdating,
    promptAssetsUpdating,
    onAddDialogLine,
    onDeleteDialogLine,
    onUpdatePromptScene,
    onUpdatePromptActors,
    onUpdatePromptProps,
    onUpdatePromptCostumes,
    selectedShot,
    onUpdateShotTitle,
    onUpdateShotScriptExcerpt,
    onDeleteShotOps,
    onClose,
    onPatchShotDetail,
    onPatchShotDetailImmediate,
    onSelectPreviewVideo,
  } = props
  const [imageVersion, setImageVersion] = useState('v1')
  const [refImageType, setRefImageType] = useState<string[]>([])
  const [useBoneDepth, setUseBoneDepth] = useState(false)
  const [audioMode, setAudioMode] = useState<'none' | 'prompt' | 'upload'>('none')
  const [hideShot, setHideShot] = useState(false)
  const [newDialogText, setNewDialogText] = useState('')
  const [creatingDialog, setCreatingDialog] = useState(false)
  const [videoPromptFrameType, setVideoPromptFrameType] = useState<PromptFrameType>('key')
  const [videoPromptGenerating, setVideoPromptGenerating] = useState(false)
  const [inspectorTabKey, setInspectorTabKey] = useState('camera')
  const [sceneNameMap, setSceneNameMap] = useState<Record<string, string>>({})
  const [characterNameMap, setCharacterNameMap] = useState<Record<string, string>>({})
  const [linkRoleOpen, setLinkRoleOpen] = useState(false)
  const [linkRoleLoading, setLinkRoleLoading] = useState(false)
  const [linkRoleSelectedIds, setLinkRoleSelectedIds] = useState<string[]>([])
  const [projectRoleOptions, setProjectRoleOptions] = useState<
    Array<{ value: string; label: React.ReactNode; searchLabel: string; disabled?: boolean }>
  >([])
  const [shotLinkedAssets, setShotLinkedAssets] = useState<
    Array<{ type: string; id: string; name?: string; thumbnail?: string; image_id?: number | null }>
  >([])
  const [shotRenderPromptLoading, setShotRenderPromptLoading] = useState(false)

  const [linkSceneOpen, setLinkSceneOpen] = useState(false)
  const [linkSceneLoading, setLinkSceneLoading] = useState(false)
  const [projectSceneOptions, setProjectSceneOptions] = useState<Array<{ value: string; label: React.ReactNode; searchLabel: string }>>([])

  const [linkPropOpen, setLinkPropOpen] = useState(false)
  const [linkPropLoading, setLinkPropLoading] = useState(false)
  const [linkPropSelectedIds, setLinkPropSelectedIds] = useState<string[]>([])
  const [projectPropOptions, setProjectPropOptions] = useState<Array<{ value: string; label: React.ReactNode; searchLabel: string; disabled?: boolean }>>([])

  const [linkCostumeOpen, setLinkCostumeOpen] = useState(false)
  const [linkCostumeLoading, setLinkCostumeLoading] = useState(false)
  const [linkCostumeSelectedIds, setLinkCostumeSelectedIds] = useState<string[]>([])
  const [projectCostumeOptions, setProjectCostumeOptions] = useState<Array<{ value: string; label: React.ReactNode; searchLabel: string; disabled?: boolean }>>([])
  const [opsTitleDraft, setOpsTitleDraft] = useState('')
  const [opsNoteDraft, setOpsNoteDraft] = useState('')
  const opsTitleSaveTimerRef = useRef<number | null>(null)
  const opsNoteSaveTimerRef = useRef<number | null>(null)
  const [keyframePromptPreviewOpen, setKeyframePromptPreviewOpen] = useState(false)
  const [keyframePromptPreviewLoading, setKeyframePromptPreviewLoading] = useState(false)
  const [keyframePromptActionLoading, setKeyframePromptActionLoading] = useState(false)
  const [keyframePromptPreviewFrameType, setKeyframePromptPreviewFrameType] = useState<PromptFrameType>('key')
  const [keyframePromptPreviewDraft, setKeyframePromptPreviewDraft] = useState('')
  const [keyframePromptPreviewRefFileIds, setKeyframePromptPreviewRefFileIds] = useState<string[]>([])
  const [videoPromptPreviewOpen, setVideoPromptPreviewOpen] = useState(false)
  const [videoPromptPreviewLoading, setVideoPromptPreviewLoading] = useState(false)
  const [videoPromptPreviewSubmitting, setVideoPromptPreviewSubmitting] = useState(false)
  const [videoPromptPreviewDraft, setVideoPromptPreviewDraft] = useState('')
  const [videoPromptPreviewImages, setVideoPromptPreviewImages] = useState<string[]>([])
  const [videoReferenceMode, setVideoReferenceMode] = useState<'first' | 'last' | 'key' | 'first_last' | 'first_last_key' | 'text_only'>('text_only')
  const [videoTaskPolling, setVideoTaskPolling] = useState(false)
  const [videoTaskStatus, setVideoTaskStatus] = useState<string | null>(null)
  const [videoTaskId, setVideoTaskId] = useState<string | null>(null)
  const [generatedVideos, setGeneratedVideos] = useState<Array<{ linkId: number; fileId: string; url: string }>>([])
  const [keyframeCards, setKeyframeCards] = useState<Record<PromptFrameType, KeyframeCardState>>({
    first: { loading: false, taskStatus: null, taskId: null, thumbs: [], modalOpen: false, applyingFileId: null },
    key: { loading: false, taskStatus: null, taskId: null, thumbs: [], modalOpen: false, applyingFileId: null },
    last: { loading: false, taskStatus: null, taskId: null, thumbs: [], modalOpen: false, applyingFileId: null },
  })
  const showAvTab = false
  const showGenRefParams = false
  const showGenRefVersions = false

  useEffect(() => {
    setHideShot(Boolean(selectedShot?.hidden))
  }, [selectedShot?.hidden])

  useEffect(() => {
    if (!selectedShot?.id) {
      setGeneratedVideos([])
      return
    }
    let canceled = false
    void (async () => {
      try {
        const links = await listTaskLinksNormalized({
          resourceType: 'video',
          relationType: 'video',
          relationEntityId: selectedShot.id,
          order: 'updated_at',
          isDesc: true,
          page: 1,
          pageSize: 100,
        })
        if (canceled) return
        const seen = new Set<string>()
        const list = links
          .filter((l) => Boolean(l.file_id))
          .map((l) => ({
            linkId: l.id,
            fileId: String(l.file_id),
            url: buildFileDownloadUrl(String(l.file_id)) ?? '',
          }))
          .filter((v) => Boolean(v.url))
          .filter((v) => {
            if (seen.has(v.fileId)) return false
            seen.add(v.fileId)
            return true
          })
        const currentId = selectedShot.generated_video_file_id?.trim() || ''
        if (currentId && !list.some((x) => x.fileId === currentId)) {
          const currentUrl = buildFileDownloadUrl(currentId) ?? ''
          if (currentUrl) list.unshift({ linkId: -1, fileId: currentId, url: currentUrl })
        }
        setGeneratedVideos(list)
      } catch {
        if (!canceled) setGeneratedVideos([])
      }
    })()
    return () => {
      canceled = true
    }
  }, [selectedShot?.id, selectedShot?.generated_video_file_id, videoTaskStatus, videoTaskPolling])

  useEffect(() => {
    setOpsTitleDraft(selectedShot?.title ?? '')
    setOpsNoteDraft(selectedShot?.script_excerpt ?? '')
    if (opsTitleSaveTimerRef.current) window.clearTimeout(opsTitleSaveTimerRef.current)
    if (opsNoteSaveTimerRef.current) window.clearTimeout(opsNoteSaveTimerRef.current)
    opsTitleSaveTimerRef.current = null
    opsNoteSaveTimerRef.current = null
  }, [selectedShot?.id])

  useEffect(() => {
    if (!selectedShot?.id) return
    if (opsTitleDraft === (selectedShot.title ?? '')) return

    if (opsTitleSaveTimerRef.current) window.clearTimeout(opsTitleSaveTimerRef.current)
    opsTitleSaveTimerRef.current = window.setTimeout(() => {
      void onUpdateShotTitle(selectedShot.id, opsTitleDraft)
      opsTitleSaveTimerRef.current = null
    }, 500)

    return () => {
      if (opsTitleSaveTimerRef.current) window.clearTimeout(opsTitleSaveTimerRef.current)
      opsTitleSaveTimerRef.current = null
    }
  }, [opsTitleDraft, selectedShot?.id, selectedShot?.title, onUpdateShotTitle])

  useEffect(() => {
    if (!selectedShot?.id) return
    if (opsNoteDraft === (selectedShot.script_excerpt ?? '')) return

    if (opsNoteSaveTimerRef.current) window.clearTimeout(opsNoteSaveTimerRef.current)
    opsNoteSaveTimerRef.current = window.setTimeout(() => {
      void onUpdateShotScriptExcerpt(selectedShot.id, opsNoteDraft)
      opsNoteSaveTimerRef.current = null
    }, 500)

    return () => {
      if (opsNoteSaveTimerRef.current) window.clearTimeout(opsNoteSaveTimerRef.current)
      opsNoteSaveTimerRef.current = null
    }
  }, [opsNoteDraft, selectedShot?.id, selectedShot?.script_excerpt, onUpdateShotScriptExcerpt])

  const flushOpsTitle = async () => {
    if (!selectedShot?.id) return
    if (opsTitleSaveTimerRef.current) window.clearTimeout(opsTitleSaveTimerRef.current)
    opsTitleSaveTimerRef.current = null
    if (opsTitleDraft === (selectedShot.title ?? '')) return
    await onUpdateShotTitle(selectedShot.id, opsTitleDraft)
  }

  const flushOpsNote = async () => {
    if (!selectedShot?.id) return
    if (opsNoteSaveTimerRef.current) window.clearTimeout(opsNoteSaveTimerRef.current)
    opsNoteSaveTimerRef.current = null
    if (opsNoteDraft === (selectedShot.script_excerpt ?? '')) return
    await onUpdateShotScriptExcerpt(selectedShot.id, opsNoteDraft)
  }

  const sceneIds = useMemo(() => Array.from(new Set(sceneLinks.map((x) => x.scene_id).filter(Boolean))), [sceneLinks])
  const characterIds = useMemo(() => Array.from(new Set(shotCharacterLinks.map((x) => x.character_id).filter(Boolean))), [shotCharacterLinks])

  const linkedCharacterIds = useMemo(() => characterIds, [characterIds])
  const linkedSceneId = useMemo(() => {
    if (!selectedShot?.id) return null
    return sceneLinks.find((l) => (l.shot_id ?? null) === selectedShot.id)?.scene_id ?? shotDetail?.scene_id ?? null
  }, [sceneLinks, selectedShot?.id, shotDetail?.scene_id])
  const linkedPropIds = useMemo(() => {
    if (!selectedShot?.id) return []
    return Array.from(new Set(propLinks.filter((l) => (l.shot_id ?? null) === selectedShot.id).map((l) => l.prop_id).filter(Boolean))) as string[]
  }, [propLinks, selectedShot?.id])
  const linkedCostumeIds = useMemo(() => {
    if (!selectedShot?.id) return []
    return Array.from(new Set(costumeLinks.filter((l) => (l.shot_id ?? null) === selectedShot.id).map((l) => l.costume_id).filter(Boolean))) as string[]
  }, [costumeLinks, selectedShot?.id])

  useEffect(() => {
    if (!selectedShot?.id) {
      setShotLinkedAssets([])
      return
    }
    let canceled = false
    void (async () => {
      try {
        const res = await StudioShotsService.listShotLinkedAssetsApiV1StudioShotsShotIdLinkedAssetsGet({
          shotId: selectedShot.id,
          page: 1,
          pageSize: 100,
        })
        if (canceled) return
        const items = (res.data?.items ?? []) as any[]
        setShotLinkedAssets(
          items
            .filter((x) => x && typeof x.type === 'string' && typeof x.id === 'string')
            .map((x) => ({
              type: String(x.type),
              id: String(x.id),
              name: typeof x.name === 'string' ? x.name : undefined,
              image_id: typeof x.image_id === 'number' ? x.image_id : x.image_id === null ? null : undefined,
              thumbnail: typeof x.thumbnail === 'string' && x.thumbnail.trim() ? x.thumbnail.trim() : undefined,
            })),
        )
      } catch {
        if (!canceled) setShotLinkedAssets([])
      }
    })()
    return () => {
      canceled = true
    }
  }, [selectedShot?.id])

  const linkedAssetThumbByKey = useMemo(() => {
    const map = new Map<string, string>()
    shotLinkedAssets.forEach((it) => {
      if (!it.thumbnail) return
      map.set(`${it.type}:${it.id}`, it.thumbnail)
    })
    return map
  }, [shotLinkedAssets])

  const extractFileIdFromThumbnail = useCallback((thumbnail?: string | null): string | null => {
    const v = (thumbnail || '').trim()
    if (!v) return null
    // 纯 file_id：不包含路径或协议
    if (!v.includes('/') && !v.includes(':')) return v
    try {
      const url = new URL(v, typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
      const m = url.pathname.match(/\/api\/v1\/studio\/files\/([^/]+)\/download\/?$/)
      if (m?.[1]) return decodeURIComponent(m[1])
    } catch {
      // ignore
    }
    return null
  }, [])

  const shotLinkedAssetNameByFileId = useMemo(() => {
    const map = new Map<string, string>()
    shotLinkedAssets.forEach((it: any) => {
      const fid =
        (typeof it?.file_id === 'string' && it.file_id.trim() ? it.file_id.trim() : null) ??
        extractFileIdFromThumbnail(it?.thumbnail ?? null)
      if (!fid) return
      const name = typeof it?.name === 'string' && it.name.trim() ? it.name.trim() : String(it?.id ?? '')
      if (!name) return
      map.set(fid, name)
    })
    return map
  }, [extractFileIdFromThumbnail, shotLinkedAssets])

  const renderShotPromptToTextarea = useCallback(
    async (opts?: { frameType?: PromptFrameType; prompt?: string | null }) => {
      if (!selectedShot?.id) return
      const frameType = opts?.frameType ?? keyframePromptPreviewFrameType
      setShotRenderPromptLoading(true)
      setKeyframePromptPreviewLoading(true)
      try {
        const imagesPayload = shotLinkedAssets
          .map((x) => {
            const fileId = extractFileIdFromThumbnail(x.thumbnail ?? null)
            return {
              type: x.type as any,
              id: x.id,
              name: x.name ?? x.id,
              file_id: fileId,
            }
          })
          .filter((x) => typeof x.file_id === 'string' && x.file_id.trim().length > 0)

        const rendered = await StudioImageTasksService.renderShotFramePromptApiV1StudioImageTasksShotShotIdFrameRenderPromptPost({
          shotId: selectedShot.id,
          requestBody: {
            frame_type: frameType,
            model_id: null,
            prompt: typeof opts?.prompt === 'string' ? opts?.prompt : opts?.prompt === null ? null : undefined,
            images: imagesPayload as any,
          } as any,
        })
        const d = rendered.data as any
        const prompt = typeof d?.prompt === 'string' ? d.prompt : ''
        const serverImages = Array.isArray(d?.images) ? (d.images as string[]).filter(Boolean) : []
        if (prompt.trim()) setKeyframePromptPreviewDraft(prompt)
        if (serverImages.length > 0) setKeyframePromptPreviewRefFileIds(serverImages)
      } catch {
        // ignore: keep existing draft
      } finally {
        setKeyframePromptPreviewLoading(false)
        setShotRenderPromptLoading(false)
      }
    },
    [extractFileIdFromThumbnail, keyframePromptPreviewFrameType, selectedShot?.id, shotLinkedAssets],
  )

  const orderedLinkedCharacterIds = useMemo(() => {
    return shotCharacterLinks
      .slice()
      .sort((a, b) => (a.index ?? 0) - (b.index ?? 0))
      .map((x) => x.character_id)
      .filter(Boolean)
      .map((x) => String(x))
  }, [shotCharacterLinks])

  const autoKeyframeRefFileIds = useMemo(() => {
    const out: string[] = []
    const push = (fid: string | null) => {
      if (!fid) return
      if (out.includes(fid)) return
      out.push(fid)
    }
    // 角色（按 index 顺序）
    orderedLinkedCharacterIds.forEach((cid) =>
      push(extractFileIdFromThumbnail(linkedAssetThumbByKey.get(`character:${cid}`) ?? null)),
    )
    // 场景（单个）
    if (linkedSceneId) push(extractFileIdFromThumbnail(linkedAssetThumbByKey.get(`scene:${linkedSceneId}`) ?? null))
    // 道具
    linkedPropIds.forEach((pid) => push(extractFileIdFromThumbnail(linkedAssetThumbByKey.get(`prop:${pid}`) ?? null)))
    // 服装
    linkedCostumeIds.forEach((cid) =>
      push(extractFileIdFromThumbnail(linkedAssetThumbByKey.get(`costume:${cid}`) ?? null)),
    )
    return out
  }, [
    extractFileIdFromThumbnail,
    linkedCostumeIds,
    linkedPropIds,
    linkedSceneId,
    linkedAssetThumbByKey,
    orderedLinkedCharacterIds,
  ])

  const loadProjectRoleOptions = async () => {
    if (!projectId) {
      setProjectRoleOptions([])
      return
    }
    setLinkRoleLoading(true)
    try {
      const res = await StudioEntitiesApi.list('character', { page: 1, pageSize: 20, q: null })
      const items = (res.data?.items ?? []).filter((x: any) => x?.project_id === projectId)
      const opts = items.map((c: any) => {
        const id = String(c?.id ?? '')
        const name = String(c?.name ?? id)
        const thumb = typeof c?.thumbnail === 'string' ? c.thumbnail : ''
        const disabled = linkedCharacterIds.includes(id)
        return {
          value: id,
          searchLabel: name,
          disabled,
          label: (
            <div className="flex items-center gap-2 min-w-0">
              {thumb ? (
                <img src={resolveAssetUrl(thumb)} alt="" className="w-6 h-6 rounded object-cover shrink-0" />
              ) : (
                <div className="w-6 h-6 rounded bg-gray-100 flex items-center justify-center text-gray-400 shrink-0">
                  <UserOutlined />
                </div>
              )}
              <div className="min-w-0 truncate">{name}</div>
            </div>
          ),
        }
      })
      setProjectRoleOptions(opts)
    } catch {
      setProjectRoleOptions([])
    } finally {
      setLinkRoleLoading(false)
    }
  }

  const loadProjectAssetOptions = async (kind: 'scene' | 'prop' | 'costume') => {
    if (!projectId) return
    if (kind === 'scene') setLinkSceneLoading(true)
    if (kind === 'prop') setLinkPropLoading(true)
    if (kind === 'costume') setLinkCostumeLoading(true)
    try {
      const res = await StudioShotLinksService.listProjectEntityLinksApiV1StudioShotLinksEntityTypeGet({
        entityType: kind,
        projectId,
        chapterId: null,
        shotId: null,
        assetId: null,
        order: null,
        isDesc: false,
        page: 1,
        pageSize: 20,
      })
      const items = (res.data?.items ?? []) as any[]
      const ids = Array.from(
        new Set(
          items
            .map((it) => (kind === 'scene' ? it.scene_id : kind === 'prop' ? it.prop_id : it.costume_id))
            .filter(Boolean)
            .map((x) => String(x)),
        ),
      )
      const details = await Promise.all(
        ids.map(async (id) => {
          try {
            const r = await StudioEntitiesApi.get(kind as any, id)
            const d = (r.data ?? null) as any
            return { id, name: String(d?.name ?? id), thumb: typeof d?.thumbnail === 'string' ? d.thumbnail : '' }
          } catch {
            return { id, name: id, thumb: '' }
          }
        }),
      )
      const nextThumbMap: Record<string, string> = {}
      details.forEach((d) => {
        if (d.thumb) nextThumbMap[d.id] = d.thumb
      })

      const makeLabel = (d: { id: string; name: string; thumb: string }) => (
        <div className="flex items-center gap-2 min-w-0">
          {d.thumb ? (
            <img src={resolveAssetUrl(d.thumb)} alt="" className="w-6 h-6 rounded object-cover shrink-0" />
          ) : (
            <div className="w-6 h-6 rounded bg-gray-100 flex items-center justify-center text-gray-400 shrink-0">
              <UserOutlined />
            </div>
          )}
          <div className="min-w-0 truncate">{d.name}</div>
        </div>
      )

      if (kind === 'scene') {
        setProjectSceneOptions(details.map((d) => ({ value: d.id, searchLabel: d.name, label: makeLabel(d) })))
      } else if (kind === 'prop') {
        setProjectPropOptions(
          details.map((d) => ({ value: d.id, searchLabel: d.name, label: makeLabel(d), disabled: linkedPropIds.includes(d.id) })),
        )
      } else {
        setProjectCostumeOptions(
          details.map((d) => ({ value: d.id, searchLabel: d.name, label: makeLabel(d), disabled: linkedCostumeIds.includes(d.id) })),
        )
      }
    } finally {
      if (kind === 'scene') setLinkSceneLoading(false)
      if (kind === 'prop') setLinkPropLoading(false)
      if (kind === 'costume') setLinkCostumeLoading(false)
    }
  }

  useEffect(() => {
    if (sceneIds.length === 0) {
      setSceneNameMap({})
      return
    }
    void (async () => {
      const entries = await Promise.all(
        sceneIds.map(async (id) => {
          try {
            const r = await StudioEntitiesApi.get('scene', id)
            const d = r.data as { name?: string } | null | undefined
            return [id, d?.name?.trim() || id] as const
          } catch {
            return [id, id] as const
          }
        }),
      )
      setSceneNameMap(Object.fromEntries(entries))
    })()
  }, [sceneIds])

  useEffect(() => {
    if (characterIds.length === 0) {
      setCharacterNameMap({})
      return
    }
    void (async () => {
      const entries = await Promise.all(
        characterIds.map(async (id) => {
          try {
            const r = await StudioEntitiesApi.get('character', id)
            const d = r.data as { name?: string; thumbnail?: string | null } | null | undefined
            const name = d?.name?.trim() || id
            const thumb = typeof d?.thumbnail === 'string' && d.thumbnail.trim() ? d.thumbnail.trim() : ''
            return { id, name, thumb }
          } catch {
            return { id, name: id, thumb: '' }
          }
        }),
      )
      const nextNameMap: Record<string, string> = {}
      entries.forEach((e) => {
        nextNameMap[e.id] = e.name
      })
      setCharacterNameMap(nextNameMap)
    })()
  }, [characterIds])

  const getPromptFromDetailByType = (frameType: PromptFrameType): string => {
    if (!shotDetail) return ''
    if (frameType === 'first') return shotDetail.first_frame_prompt ?? ''
    if (frameType === 'last') return shotDetail.last_frame_prompt ?? ''
    return shotDetail.key_frame_prompt ?? ''
  }

  const patchPromptToDetailByType = (frameType: PromptFrameType, prompt: string) => {
    if (frameType === 'first') {
      onPatchShotDetail({ first_frame_prompt: prompt })
      return
    }
    if (frameType === 'last') {
      onPatchShotDetail({ last_frame_prompt: prompt })
      return
    }
    onPatchShotDetail({ key_frame_prompt: prompt })
  }

  const frameLabel: Record<PromptFrameType, string> = { first: '首帧', key: '关键帧', last: '尾帧' }
  const refFrameTypeOptions = useMemo(() => {
    const kinds = new Set((frameImages ?? []).map((x) => x.frame_type))
    const opts: Array<{ value: string; label: string }> = []
    if (kinds.has('first')) opts.push({ value: 'first', label: '首帧' })
    if (kinds.has('last')) opts.push({ value: 'last', label: '尾帧' })
    if (kinds.has('first') && kinds.has('last')) opts.push({ value: 'first_last', label: '首尾帧' })
    if (kinds.has('key')) opts.push({ value: 'key', label: '关键帧' })
    return opts
  }, [frameImages])

  useEffect(() => {
    const allowed = new Set(refFrameTypeOptions.map((x) => x.value))
    setRefImageType((prev) => prev.filter((v) => allowed.has(v)))
  }, [refFrameTypeOptions])

  const buildVideoRefSelection = () => {
    const selected = new Set(refImageType)
    const first = frameImages.find((x) => x.frame_type === 'first')?.file_id ?? null
    const last = frameImages.find((x) => x.frame_type === 'last')?.file_id ?? null
    const key = frameImages.find((x) => x.frame_type === 'key')?.file_id ?? null

    const useFirst = selected.has('first') || selected.has('first_last')
    const useLast = selected.has('last') || selected.has('first_last')
    const useKey = selected.has('key')

    if (useFirst && useLast && useKey) {
      return {
        referenceMode: 'first_last_key' as const,
        images: [first, last, key].filter((x): x is string => Boolean(x)),
      }
    }
    if (useFirst && useLast) {
      return {
        referenceMode: 'first_last' as const,
        images: [first, last].filter((x): x is string => Boolean(x)),
      }
    }
    if (useKey) return { referenceMode: 'key' as const, images: key ? [key] : [] }
    if (useFirst) return { referenceMode: 'first' as const, images: first ? [first] : [] }
    if (useLast) return { referenceMode: 'last' as const, images: last ? [last] : [] }
    return { referenceMode: 'text_only' as const, images: [] }
  }

  const openVideoPromptPreview = async () => {
    if (!selectedShot?.id) {
      message.warning('请先选择一个分镜')
      return
    }
    const { referenceMode, images } = buildVideoRefSelection()
    setVideoReferenceMode(referenceMode)
    setVideoPromptPreviewOpen(true)
    setVideoPromptPreviewLoading(true)
    try {
      const res = await FilmService.previewVideoGenerationPromptApiV1FilmTasksVideoPreviewPromptPost({
        requestBody: {
          shot_id: selectedShot.id,
          reference_mode: referenceMode,
          prompt: null,
          images,
        } as any,
      })
      const d = res.data as any
      setVideoPromptPreviewDraft(typeof d?.prompt === 'string' ? d.prompt : '')
      setVideoPromptPreviewImages(Array.isArray(d?.images) ? (d.images as string[]) : [])
    } catch {
      message.error('获取视频提示词预览失败')
    } finally {
      setVideoPromptPreviewLoading(false)
    }
  }

  const submitVideoGeneration = async () => {
    if (!selectedShot?.id) {
      message.warning('请先选择一个分镜')
      return
    }
    const prompt = (videoPromptPreviewDraft || '').trim()
    if (!prompt) {
      message.warning('请输入视频提示词')
      return
    }
    setVideoPromptPreviewSubmitting(true)
    try {
      const created = await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
        requestBody: {
          shot_id: selectedShot.id,
          reference_mode: videoReferenceMode,
          prompt,
          images: videoPromptPreviewImages,
        } as any,
      })
      const taskId = created.data?.task_id
      if (!taskId) {
        message.error('视频生成任务创建失败：缺少任务 ID')
        return
      }
      message.success('已创建视频生成任务')
      setVideoTaskId(taskId)
      setVideoTaskStatus('pending')
      setVideoTaskPolling(true)
      setVideoPromptPreviewOpen(false)
    } catch {
      message.error('发起视频生成失败')
    } finally {
      setVideoPromptPreviewSubmitting(false)
    }
  }

  useEffect(() => {
    if (!videoTaskPolling || !videoTaskId) return
    let cancelled = false
    void (async () => {
      try {
        let finalStatus: string | null = null
        for (let i = 0; i < 60; i += 1) {
          await sleep(2000)
          if (cancelled) return
          const statusRes = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId: videoTaskId })
          const status = statusRes.data?.status ?? null
          if (!status) continue
          finalStatus = status
          setVideoTaskStatus(status)
          if (status === 'succeeded' || status === 'failed' || status === 'cancelled') break
        }
        if (!cancelled && finalStatus && (finalStatus === 'failed' || finalStatus === 'cancelled')) {
          message.error('视频生成任务失败')
        }
      } catch {
        if (!cancelled) {
          message.error('获取视频任务状态失败')
        }
      } finally {
        if (!cancelled) setVideoTaskPolling(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [videoTaskPolling, videoTaskId])
  const updateCardState = (frameType: PromptFrameType, patch: Partial<KeyframeCardState>) => {
    setKeyframeCards((prev) => ({ ...prev, [frameType]: { ...prev[frameType], ...patch } }))
  }

  const getLatestFrameSlotId = async (frameType: PromptFrameType): Promise<number | null> => {
    if (!selectedShot?.id) return null
    const res = await StudioShotFrameImagesService.listShotFrameImagesApiV1StudioShotFrameImagesGet({
      shotDetailId: selectedShot.id,
      order: null,
      isDesc: false,
      page: 1,
      pageSize: 100,
    })
    const items = (res.data?.items ?? []) as ShotFrameImageRead[]
    const slot = items.find((x) => x.frame_type === frameType)
    return slot?.id ?? null
  }

  const loadCardThumbs = async (frameType: PromptFrameType, slotIdOverride?: number | null, retryCount = 1) => {
    const localSlotId = frameImages.find((x) => x.frame_type === frameType)?.id ?? null
    const slotId = slotIdOverride ?? localSlotId ?? (await getLatestFrameSlotId(frameType))
    if (!slotId) {
      updateCardState(frameType, { thumbs: [] })
      return
    }
    let thumbs: Array<{ linkId: number; fileId: string; thumbUrl: string }> = []
    for (let i = 0; i < retryCount; i += 1) {
      const links = await listTaskLinksNormalized({
        resourceType: 'image',
        relationType: 'shot_frame_image',
        relationEntityId: String(slotId),
        order: 'updated_at',
        isDesc: true,
        page: 1,
        pageSize: 100,
      })
      const seen = new Set<string>()
      thumbs = links
        .filter((l) => Boolean(l.file_id))
        .filter((l) => {
          const fid = String(l.file_id)
          if (seen.has(fid)) return false
          seen.add(fid)
          return true
        })
        .map((l) => ({
          linkId: l.id,
          fileId: String(l.file_id),
          thumbUrl: buildFileDownloadUrl(String(l.file_id)) ?? '',
        }))
      if (thumbs.length > 0 || i === retryCount - 1) break
      await sleep(800)
    }
    updateCardState(frameType, { thumbs })
  }

  const generateKeyframeCard = async (frameType: PromptFrameType) => {
    if (!selectedShot?.id) {
      message.warning('请先选择一个分镜')
      return
    }
    try {
      setKeyframePromptPreviewLoading(true)
      setKeyframePromptPreviewOpen(true)
      setKeyframePromptPreviewFrameType(frameType)
      setKeyframePromptPreviewRefFileIds(autoKeyframeRefFileIds)
      // 文本区域内容：统一由 frame-render-prompt 获取
      void renderShotPromptToTextarea({ frameType, prompt: getPromptFromDetailByType(frameType) })
    } catch {
      message.error('获取提示词失败')
    } finally {
      // loading 由 renderShotPromptToTextarea 结束后关闭
    }
  }

  const regenerateKeyframePrompt = async () => {
    if (!selectedShot?.id) {
      message.warning('请先选择一个分镜')
      return
    }
    const frameType = keyframePromptPreviewFrameType
    setKeyframePromptActionLoading(true)
    setKeyframePromptPreviewLoading(true)
    try {
      const created = await FilmService.createShotFramePromptTaskApiV1FilmTasksShotFramePromptsPost({
        requestBody: {
          shot_id: selectedShot.id,
          frame_type: frameType,
        },
      })
      const taskId = created.data?.task_id
      if (!taskId) {
        message.error('生成任务创建失败：缺少任务 ID')
        return
      }

      let finalStatus = 'pending'
      for (let i = 0; i < 30; i += 1) {
        await sleep(2000)
        const statusRes = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId })
        const status = statusRes.data?.status
        if (!status) continue
        finalStatus = status
        if (status === 'succeeded' || status === 'failed' || status === 'cancelled') break
      }

      if (finalStatus !== 'succeeded') {
        if (finalStatus === 'failed' || finalStatus === 'cancelled') {
          message.error('生成提示词失败')
        } else {
          message.warning('生成任务仍在执行，请稍后重试')
        }
        return
      }

      const resultRes = await FilmService.getTaskResultApiV1FilmTasksTaskIdResultGet({ taskId })
      const result = (resultRes.data?.result ?? null) as Record<string, unknown> | null
      const generatedPrompt = typeof result?.prompt === 'string' ? result.prompt : ''
      if (!generatedPrompt.trim()) {
        message.warning('生成完成，但未返回提示词')
        return
      }
      // 文本区域内容：改为以 frame-render-prompt 的返回为准
      await renderShotPromptToTextarea({ frameType, prompt: generatedPrompt })
      message.success('提示词已生成')
    } catch {
      message.error('生成提示词失败')
    } finally {
      setKeyframePromptActionLoading(false)
    }
  }

  useEffect(() => {
    // 弹窗打开时，若当前没有参考图，则自动填充为分镜关联实体的参考图
    if (!keyframePromptPreviewOpen) return
    if (keyframePromptPreviewRefFileIds.length > 0) return
    if (autoKeyframeRefFileIds.length === 0) return
    setKeyframePromptPreviewRefFileIds(autoKeyframeRefFileIds)
  }, [autoKeyframeRefFileIds, keyframePromptPreviewOpen, keyframePromptPreviewRefFileIds.length])

  const confirmGenerateKeyframeWithPrompt = async () => {
    if (!selectedShot?.id) {
      message.warning('请先选择一个分镜')
      return
    }
    const frameType = keyframePromptPreviewFrameType
    const prompt = (keyframePromptPreviewDraft || '').trim()
    if (!prompt) {
      message.warning('请输入提示词')
      return
    }

    setKeyframePromptActionLoading(true)
    updateCardState(frameType, { loading: true, taskStatus: 'pending', taskId: null })
    try {
      // 若当前预览未携带参考图（例如直接打开未生成过），自动补齐为当前分镜关联实体的参考图
      const refFileIds = keyframePromptPreviewRefFileIds.length > 0 ? keyframePromptPreviewRefFileIds : autoKeyframeRefFileIds
      const imagesPayload = refFileIds.map((fid) => {
        const match =
          shotLinkedAssets.find((x) => extractFileIdFromThumbnail(x.thumbnail ?? null) === fid) ??
          shotLinkedAssets.find((x) => (x as any)?.file_id === fid)
        // 后端 ShotLinkedAssetItem: type/id/name 必填；file_id 用于参考图
        return {
          type: (match?.type as any) ?? 'character',
          id: match?.id ?? fid,
          name: match?.name ?? match?.id ?? fid,
          file_id: fid,
        }
      })
      const created = await StudioImageTasksService.createShotFrameImageGenerationTaskApiV1StudioImageTasksShotShotIdFrameImageTasksPost({
        shotId: selectedShot.id,
        requestBody: {
          frame_type: frameType,
          model_id: null,
          prompt,
          images: imagesPayload,
        } as any,
      })
      const taskId = created.data?.task_id
      if (!taskId) {
        message.error('生成任务创建失败：缺少任务 ID')
        updateCardState(frameType, { loading: false, taskStatus: 'failed' })
        return
      }
      updateCardState(frameType, { taskId })

      let finalStatus = 'pending'
      for (let i = 0; i < 30; i += 1) {
        await sleep(2000)
        const statusRes = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId })
        const status = statusRes.data?.status
        if (!status) continue
        finalStatus = status
        updateCardState(frameType, { taskStatus: status })
        if (status === 'succeeded' || status === 'failed' || status === 'cancelled') break
      }
      if (finalStatus === 'succeeded') {
        const latestSlotId = await getLatestFrameSlotId(frameType)
        await loadCardThumbs(frameType, latestSlotId, 5)
        setKeyframePromptPreviewOpen(false)
      } else if (finalStatus === 'failed' || finalStatus === 'cancelled') {
        message.error(`${frameLabel[frameType]}生成失败`)
      } else {
        message.warning('生成任务仍在执行，请稍后刷新')
      }
    } catch {
      updateCardState(frameType, { taskStatus: 'failed' })
      message.error(`${frameLabel[frameType]}生成失败`)
    } finally {
      updateCardState(frameType, { loading: false })
      setKeyframePromptActionLoading(false)
    }
  }

  const applyCardImage = async (frameType: PromptFrameType, fileId: string) => {
    const slot = frameImages.find((x) => x.frame_type === frameType)
    if (!slot) return
    updateCardState(frameType, { applyingFileId: fileId })
    try {
      await StudioShotFrameImagesService.updateShotFrameImageApiV1StudioShotFrameImagesImageIdPatch({
        imageId: slot.id,
        requestBody: { file_id: fileId } as any,
      })
      await loadCardThumbs(frameType)
      message.success('已切换使用图片')
    } catch {
      message.error('切换失败')
    } finally {
      updateCardState(frameType, { applyingFileId: null })
    }
  }

  useEffect(() => {
    if (!selectedShot?.id) return
    void Promise.all([loadCardThumbs('first'), loadCardThumbs('key'), loadCardThumbs('last')])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedShot?.id, frameImages.map((x) => `${x.id}:${x.file_id ?? ''}`).join('|')])

  const handleGenerateVideoPrompt = async () => {
    if (!selectedShot?.id) {
      message.warning('请先选择一个分镜')
      return
    }

    setVideoPromptGenerating(true)
    try {
      const created = await FilmService.createShotFramePromptTaskApiV1FilmTasksShotFramePromptsPost({
        requestBody: {
          shot_id: selectedShot.id,
          frame_type: videoPromptFrameType,
        },
      })
      const taskId = created.data?.task_id
      if (!taskId) {
        message.error('生成任务创建失败：缺少任务 ID')
        return
      }

      let finalStatus = 'pending'
      for (let i = 0; i < 30; i += 1) {
        await sleep(2000)
        const statusRes = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId })
        const status = statusRes.data?.status
        if (!status) continue
        finalStatus = status
        if (status === 'succeeded' || status === 'failed' || status === 'cancelled') break
      }

      if (finalStatus === 'succeeded') {
        const resultRes = await FilmService.getTaskResultApiV1FilmTasksTaskIdResultGet({ taskId })
        const result = (resultRes.data?.result ?? null) as Record<string, unknown> | null
        const prompt = typeof result?.prompt === 'string' ? result.prompt : ''
        if (!prompt.trim()) {
          message.warning('生成完成，但未返回提示词')
          return
        }
        patchPromptToDetailByType(videoPromptFrameType, prompt)
        message.success('视频提示词已生成')
        return
      }

      if (finalStatus === 'failed' || finalStatus === 'cancelled') {
        message.error('视频提示词生成失败')
      } else {
        message.warning('生成任务仍在执行，请稍后重试')
      }
    } catch {
      message.error('发起视频提示词生成失败')
    } finally {
      setVideoPromptGenerating(false)
    }
  }

  return (
    <div className="w-full h-full flex flex-col min-h-0">
      <div className="cs-inspector-header flex items-center justify-between">
        <div className="min-w-0">
          <div className="font-medium truncate">分镜属性面板</div>
          <div className="text-xs text-gray-500 truncate">
            {selectedShot ? `${String(selectedShot.index).padStart(2, '0')} · ${selectedShot.title}` : '未选择分镜'}
          </div>
        </div>
        <Space size="small">
          <Tooltip title="收起">
            <Button size="small" type="text" icon={<DoubleRightOutlined />} onClick={onClose} />
          </Tooltip>
        </Space>
      </div>

      <div className="cs-inspector flex-1 min-h-0 overflow-auto">
        <Tabs
          tabPosition="left"
          activeKey={inspectorTabKey}
          onChange={setInspectorTabKey}
          items={[
            {
              key: 'ops',
              label: '分镜操作',
              children: (
                <div>
                  <div className="cs-group">
                    <div className="cs-group-title">
                      <EditOutlined /> 基本
                    </div>
                    <div className="space-y-3">
                      <div>
                        <div className="text-gray-500 text-xs mb-1">分镜标题</div>
                        <Input
                          value={opsTitleDraft}
                          placeholder="分镜标题…"
                          onChange={(e) => setOpsTitleDraft(e.target.value)}
                          onBlur={() => {
                            void flushOpsTitle()
                          }}
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-medium">隐藏此分镜</div>
                          <div className="text-xs text-gray-500">隐藏后将不参与预览整章与导出</div>
                        </div>
                        <Switch checked={hideShot} onChange={setHideShot} />
                      </div>
                    </div>
                  </div>

                  <div className="cs-group">
                    <div className="cs-group-title">
                      <FileTextOutlined /> 分镜内容
                    </div>
                    <TextArea
                      rows={3}
                      value={opsNoteDraft}
                      placeholder="备注…"
                      onChange={(e) => setOpsNoteDraft(e.target.value)}
                      onBlur={() => {
                        void flushOpsNote()
                      }}
                    />
                  </div>

                  <div className="cs-group">
                    <div className="cs-group-title">
                      <AppstoreOutlined /> 操作
                    </div>
                    <Space wrap>
                      <Button
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => {
                          if (!selectedShot?.id) return
                          Modal.confirm({
                            title: '删除分镜？',
                            content: '此操作不可撤销。',
                            okText: '删除',
                            okButtonProps: { danger: true },
                            cancelText: '取消',
                            onOk: () => onDeleteShotOps(selectedShot.id),
                          })
                        }}
                      >
                        删除
                      </Button>
                    </Space>
                  </div>
                </div>
              ),
            },
            {
              key: 'camera',
              label: '镜头语言',
              children: (
                <div>
                  {loadingDetail ? (
                    <div className="text-gray-500">加载中…</div>
                  ) : shotDetail ? (
                    <>
                      <div className="cs-group">
                        <div className="cs-group-title">
                          <CameraOutlined /> 镜头语言
                        </div>
                        <div className="space-y-4">
                          <div>
                            <div className="text-gray-500 text-xs mb-1">景别</div>
                            <Radio.Group
                              value={shotDetail.camera_shot}
                              optionType="button"
                              buttonStyle="solid"
                              size="small"
                              options={CAMERA_SHOT_OPTIONS}
                              onChange={(e) => void onPatchShotDetailImmediate({ camera_shot: e.target.value })}
                              disabled={cameraUpdating}
                            />
                          </div>
                          <div>
                            <div className="text-gray-500 text-xs mb-1">角度</div>
                            <Radio.Group
                              value={shotDetail.angle}
                              optionType="button"
                              size="small"
                              options={CAMERA_ANGLE_OPTIONS}
                              onChange={(e) => void onPatchShotDetailImmediate({ angle: e.target.value })}
                              disabled={cameraUpdating}
                            />
                          </div>
                          <div>
                            <div className="text-gray-500 text-xs mb-1">运镜</div>
                            <Radio.Group
                              value={shotDetail.movement}
                              size="small"
                              options={CAMERA_MOVEMENT_OPTIONS}
                              onChange={(e) => void onPatchShotDetailImmediate({ movement: e.target.value })}
                              disabled={cameraUpdating}
                            />
                          </div>
                          <div>
                            <div className="text-gray-500 text-xs mb-1">时长（1–30s，整数）</div>
                            <div className="flex items-center gap-2">
                              <Slider
                                min={1}
                                max={30}
                                step={1}
                                value={Math.max(1, Math.min(30, Math.round(shotDetail.duration ?? 1)))}
                                style={{ flex: 1 }}
                                onChange={(v) => void onPatchShotDetailImmediate({ duration: Math.round(Number(v)) })}
                                disabled={cameraUpdating}
                              />
                              <Input
                                size="small"
                                value={`${Math.max(1, Math.min(30, Math.round(shotDetail.duration ?? 1)))}`}
                                style={{ width: 72 }}
                                onChange={(e) => {
                                  const raw = Number(e.target.value)
                                  if (!Number.isFinite(raw)) return
                                  const n = Math.max(1, Math.min(30, Math.round(raw)))
                                  void onPatchShotDetailImmediate({ duration: n })
                                }}
                                disabled={cameraUpdating}
                              />
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="cs-group">
                        <div className="cs-group-title">
                          <TagOutlined /> 情绪标签
                        </div>
                        <div className="cs-hint">用标签快速标记镜头情绪，便于生成风格统一。</div>
                        <div className="mt-3">
                          <Space wrap>
                            {['愤怒', '反转', '紧张', '温馨', '压抑'].map((t) => (
                              <Tag key={t} className="cursor-pointer">
                                {t}
                              </Tag>
                            ))}
                            <Button size="small" type="dashed">
                              + 自定义
                            </Button>
                          </Space>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="text-gray-500">请选择分镜</div>
                  )}
                </div>
              ),
            },
            {
              key: 'prompt_image',
              label: '画面描述',
              children: (
                <div>
                  <div className="cs-group">
                    <div className="cs-group-title">
                      <PictureOutlined /> 画面要素
                    </div>
                    <div className="space-y-4">
                      <div>
                        <div className="text-gray-500 text-xs mb-1">场景</div>
                        <Select
                          showSearch
                          placeholder="选择当前镜头场景"
                          className="w-full"
                          value={sceneLinks.find((x) => (x.shot_id ?? null) === selectedShot?.id)?.scene_id ?? shotDetail?.scene_id ?? undefined}
                          onChange={(v) => void onUpdatePromptScene(typeof v === 'string' ? v : undefined)}
                          allowClear
                          disabled={promptAssetsUpdating}
                          optionLabelProp="label"
                          options={sceneIds.map((id) => ({ value: id, label: sceneNameMap[id] ?? id }))}
                        />
                      </div>
                      <div>
                        <div className="text-gray-500 text-xs mb-1">角色</div>
                        <Select
                          mode="multiple"
                          placeholder="多选当前镜头角色"
                          className="w-full"
                          value={Array.from(new Set(shotCharacterLinks.map((x) => x.character_id)))}
                          onChange={(vals) => void onUpdatePromptActors((vals as Array<string | number>).map((v) => String(v)))}
                          disabled={promptAssetsUpdating}
                          optionLabelProp="label"
                          options={characterIds.map((id) => ({ value: id, label: characterNameMap[id] ?? id }))}
                        />
                      </div>
                      <div>
                        <div className="text-gray-500 text-xs mb-1">对白（说话人 + 富文本占位）</div>
                        <Space.Compact className="w-full">
                          <Select
                            size="small"
                            style={{ width: 120 }}
                            options={[
                              { value: '小雨', label: '小雨' },
                              { value: '阿川', label: '阿川' },
                            ]}
                            placeholder="说话人"
                            disabled
                          />
                          <Input
                            size="small"
                            placeholder="输入对白，回车添加…"
                            value={newDialogText}
                            onChange={(e) => setNewDialogText(e.target.value)}
                            onPressEnter={async () => {
                              if (creatingDialog) return
                              setCreatingDialog(true)
                              try {
                                await onAddDialogLine(newDialogText)
                                setNewDialogText('')
                              } catch {
                                message.error('添加对白失败')
                              } finally {
                                setCreatingDialog(false)
                              }
                            }}
                          />
                        </Space.Compact>
                        {dialogLines.length > 0 && (
                          <div className="mt-2 space-y-1">
                            {dialogLines.slice().sort((a, b) => (a.index ?? 0) - (b.index ?? 0)).map((l) => (
                              <div key={l.id} className="flex items-center gap-2">
                                <div className="text-xs text-gray-600 truncate flex-1 min-w-0">{l.text}</div>
                                <Button
                                  size="small"
                                  type="text"
                                  danger
                                  icon={<DeleteOutlined />}
                                  onClick={() => {
                                    Modal.confirm({
                                      title: '删除该对白？',
                                      okText: '删除',
                                      cancelText: '取消',
                                      okButtonProps: { danger: true },
                                      onOk: async () => {
                                        try {
                                          await onDeleteDialogLine(l.id)
                                          message.success('已删除')
                                        } catch {
                                          message.error('删除失败')
                                        }
                                      },
                                    })
                                  }}
                                />
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                      <div>
                        <div className="flex items-center justify-between">
                          <div className="text-gray-500 text-xs">氛围描述</div>
                          <Switch
                            size="small"
                            checked={shotDetail?.follow_atmosphere ?? false}
                            onChange={(v) => onPatchShotDetail({ follow_atmosphere: v })}
                          />
                        </div>
                        <TextArea
                          rows={3}
                          placeholder="氛围描述…（可选跟随画面）"
                          value={shotDetail?.atmosphere ?? ''}
                          onChange={(e) => onPatchShotDetail({ atmosphere: e.target.value })}
                        />
                      </div>
                    </div>
                  </div>

                </div>
              ),
            },
            {
              key: 'prompt_video',
              label: '视频提示词',
              children: (
                <div className="cs-group">
                  <div className="cs-group-title">
                    <FileTextOutlined /> 视频提示词
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <Select<PromptFrameType>
                      size="small"
                      value={videoPromptFrameType}
                      onChange={setVideoPromptFrameType}
                      style={{ width: 120 }}
                      options={[
                        { value: 'first', label: '首帧' },
                        { value: 'key', label: '关键帧' },
                        { value: 'last', label: '尾帧' },
                      ]}
                    />
                    <Button size="small" type="primary" loading={videoPromptGenerating} onClick={handleGenerateVideoPrompt}>
                      生成
                    </Button>
                  </div>
                  <TextArea
                    rows={8}
                    placeholder="独立视频提示词（支持多版本管理）…"
                    className="font-mono text-xs"
                    value={getPromptFromDetailByType(videoPromptFrameType)}
                    onChange={(e) => patchPromptToDetailByType(videoPromptFrameType, e.target.value)}
                  />
                  <div className="cs-hint mt-2">多版本管理：可结合右侧“生成与参考”一起迭代。</div>
                </div>
              ),
            },
            {
              key: 'keyframe_gen',
              label: '关键帧生成',
              children: (
                <div className="space-y-3">
                  {(['first', 'key', 'last'] as PromptFrameType[]).map((ft) => {
                    const st = keyframeCards[ft]
                    const slot = frameImages.find((x) => x.frame_type === ft)
                    const inUseFileId = slot?.file_id ? String(slot.file_id) : ''
                    const statusText =
                      st.taskStatus === 'pending'
                        ? '排队中'
                        : st.taskStatus === 'running'
                          ? '生成中'
                          : st.taskStatus === 'succeeded'
                            ? '已完成'
                            : st.taskStatus === 'failed'
                              ? '失败'
                              : st.taskStatus === 'cancelled'
                                ? '已取消'
                                : ''
                    return (
                      <div key={ft} className="cs-group">
                        <div className="cs-group-title flex items-center justify-between gap-2">
                          <span>{frameLabel[ft]}图片</span>
                          <Space size={8}>
                            {st.thumbs.length > 0 ? (
                              <Button size="small" type="link" onClick={() => updateCardState(ft, { modalOpen: true })}>
                                更多
                              </Button>
                            ) : null}
                            <Button size="small" type="primary" loading={st.loading} onClick={() => void generateKeyframeCard(ft)}>
                              生成
                            </Button>
                          </Space>
                        </div>
                        <div className="text-xs text-gray-500 min-h-5">{statusText}</div>
                        {st.thumbs.length === 0 ? (
                          <div className="mt-2 h-24 border border-dashed rounded flex items-center justify-center text-xs text-gray-400">暂无图片</div>
                        ) : (
                          <div className="mt-2 flex items-center gap-2 overflow-x-auto whitespace-nowrap pb-1">
                            {st.thumbs.slice(0, 4).map((it) => (
                              <img key={it.linkId} src={it.thumbUrl} alt="" className="w-16 h-16 rounded object-cover border border-gray-200 shrink-0" />
                            ))}
                          </div>
                        )}
                        <Modal title={`${frameLabel[ft]}图片`} open={st.modalOpen} onCancel={() => updateCardState(ft, { modalOpen: false })} footer={null} width={720}>
                          {ft === 'first' ? (
                            <div className="mb-3">
                              <div className="text-sm text-gray-600 mb-2">关联角色</div>
                              <div className="flex items-center gap-2 overflow-x-auto pb-1">
                                <button
                                  type="button"
                                  className="w-12 h-12 rounded border border-dashed border-gray-300 flex items-center justify-center text-gray-500 shrink-0 hover:border-gray-400 hover:text-gray-700"
                                  disabled={promptAssetsUpdating || linkRoleLoading}
                                  onClick={() => {
                                    setLinkRoleSelectedIds([])
                                    setLinkRoleOpen(true)
                                    void loadProjectRoleOptions()
                                  }}
                                  title="添加关联角色"
                                >
                                  <PlusOutlined />
                                </button>
                                {linkedCharacterIds.length === 0 ? (
                                  <div className="text-xs text-gray-400">暂无关联角色</div>
                                ) : (
                                  linkedCharacterIds.map((cid) => {
                                    const thumb = linkedAssetThumbByKey.get(`character:${cid}`)
                                    const name = characterNameMap[cid] ?? cid
                                    return thumb ? (
                                    <Image
                                        key={cid}
                                        width={48}
                                        height={48}
                                        style={{ objectFit: 'cover', borderRadius: 8 }}
                                        src={resolveAssetUrl(thumb)}
                                        preview={{ src: resolveAssetUrl(thumb) }}
                                      />
                                    ) : (
                                      <div
                                        key={cid}
                                        title={name}
                                        className="w-12 h-12 rounded bg-gray-100 flex items-center justify-center text-gray-400 shrink-0"
                                      >
                                        <UserOutlined />
                                      </div>
                                    )
                                  })
                                )}
                              </div>

                              <div className="mt-3 text-sm text-gray-600 mb-2">关联场景</div>
                              <div className="flex items-center gap-2 overflow-x-auto pb-1">
                                <button
                                  type="button"
                                  className="w-12 h-12 rounded border border-dashed border-gray-300 flex items-center justify-center text-gray-500 shrink-0 hover:border-gray-400 hover:text-gray-700"
                                  disabled={promptAssetsUpdating || linkSceneLoading}
                                  onClick={() => {
                                    setLinkSceneOpen(true)
                                    void loadProjectAssetOptions('scene')
                                  }}
                                  title="添加/更换关联场景"
                                >
                                  <PlusOutlined />
                                </button>
                                {linkedSceneId ? (
                                  linkedAssetThumbByKey.get(`scene:${linkedSceneId}`) ? (
                                    <Image
                                      key={linkedSceneId}
                                      width={48}
                                      height={48}
                                      style={{ objectFit: 'cover', borderRadius: 8 }}
                                      src={resolveAssetUrl(linkedAssetThumbByKey.get(`scene:${linkedSceneId}`) ?? '')}
                                      preview={{ src: resolveAssetUrl(linkedAssetThumbByKey.get(`scene:${linkedSceneId}`) ?? '') }}
                                    />
                                  ) : (
                                    <div className="text-xs text-gray-400">已关联场景：{sceneNameMap[linkedSceneId] ?? linkedSceneId}</div>
                                  )
                                ) : (
                                  <div className="text-xs text-gray-400">暂无关联场景</div>
                                )}
                              </div>

                              <div className="mt-3 text-sm text-gray-600 mb-2">关联道具</div>
                              <div className="flex items-center gap-2 overflow-x-auto pb-1">
                                <button
                                  type="button"
                                  className="w-12 h-12 rounded border border-dashed border-gray-300 flex items-center justify-center text-gray-500 shrink-0 hover:border-gray-400 hover:text-gray-700"
                                  disabled={promptAssetsUpdating || linkPropLoading}
                                  onClick={() => {
                                    setLinkPropSelectedIds([])
                                    setLinkPropOpen(true)
                                    void loadProjectAssetOptions('prop')
                                  }}
                                  title="添加关联道具"
                                >
                                  <PlusOutlined />
                                </button>
                                {linkedPropIds.length === 0 ? (
                                  <div className="text-xs text-gray-400">暂无关联道具</div>
                                ) : (
                                  linkedPropIds.map((pid) =>
                                    linkedAssetThumbByKey.get(`prop:${pid}`) ? (
                                      <Image
                                        key={pid}
                                        width={48}
                                        height={48}
                                        style={{ objectFit: 'cover', borderRadius: 8 }}
                                        src={resolveAssetUrl(linkedAssetThumbByKey.get(`prop:${pid}`) ?? '')}
                                        preview={{ src: resolveAssetUrl(linkedAssetThumbByKey.get(`prop:${pid}`) ?? '') }}
                                      />
                                    ) : (
                                      <div key={pid} className="w-12 h-12 rounded bg-gray-100 flex items-center justify-center text-gray-400 shrink-0">
                                        <UserOutlined />
                                      </div>
                                    ),
                                  )
                                )}
                              </div>

                              <div className="mt-3 text-sm text-gray-600 mb-2">关联服装</div>
                              <div className="flex items-center gap-2 overflow-x-auto pb-1">
                                <button
                                  type="button"
                                  className="w-12 h-12 rounded border border-dashed border-gray-300 flex items-center justify-center text-gray-500 shrink-0 hover:border-gray-400 hover:text-gray-700"
                                  disabled={promptAssetsUpdating || linkCostumeLoading}
                                  onClick={() => {
                                    setLinkCostumeSelectedIds([])
                                    setLinkCostumeOpen(true)
                                    void loadProjectAssetOptions('costume')
                                  }}
                                  title="添加关联服装"
                                >
                                  <PlusOutlined />
                                </button>
                                {linkedCostumeIds.length === 0 ? (
                                  <div className="text-xs text-gray-400">暂无关联服装</div>
                                ) : (
                                  linkedCostumeIds.map((cid) =>
                                    linkedAssetThumbByKey.get(`costume:${cid}`) ? (
                                      <Image
                                        key={cid}
                                        width={48}
                                        height={48}
                                        style={{ objectFit: 'cover', borderRadius: 8 }}
                                        src={resolveAssetUrl(linkedAssetThumbByKey.get(`costume:${cid}`) ?? '')}
                                        preview={{ src: resolveAssetUrl(linkedAssetThumbByKey.get(`costume:${cid}`) ?? '') }}
                                      />
                                    ) : (
                                      <div key={cid} className="w-12 h-12 rounded bg-gray-100 flex items-center justify-center text-gray-400 shrink-0">
                                        <UserOutlined />
                                      </div>
                                    ),
                                  )
                                )}
                              </div>
                            </div>
                          ) : null}

                          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                            {st.thumbs.map((it) => {
                              const inUse = inUseFileId && inUseFileId === it.fileId
                              return (
                                <div key={it.linkId} className="border rounded p-2">
                                  <img src={it.thumbUrl} alt="" className="w-full h-36 object-cover rounded" />
                                  <div className="mt-2 flex items-center justify-between">
                                    {inUse ? (
                                      <Tag color="green">使用中</Tag>
                                    ) : (
                                      <Button size="small" loading={st.applyingFileId === it.fileId} onClick={() => void applyCardImage(ft, it.fileId)}>
                                        使用
                                      </Button>
                                    )}
                                  </div>
                                </div>
                              )
                            })}
                          </div>

                          <Modal
                            title="关联角色"
                            open={linkRoleOpen}
                            onCancel={() => setLinkRoleOpen(false)}
                            footer={null}
                            destroyOnClose
                            width={560}
                          >
                            <div className="space-y-2">
                              <div className="text-xs text-gray-500">来源：当前项目全部角色（选择后立即保存；已关联的角色不可重复选择）</div>
                              <Select
                                mode="multiple"
                                className="w-full"
                                placeholder="选择要关联到当前分镜的角色"
                                value={linkRoleSelectedIds}
                                loading={linkRoleLoading}
                                disabled={promptAssetsUpdating}
                                options={projectRoleOptions}
                                optionFilterProp="searchLabel"
                                showSearch
                                filterOption={(input: string, option?: any) =>
                                  String(option?.searchLabel ?? '').toLowerCase().includes(input.toLowerCase())
                                }
                                onChange={(vals: Array<string | number>) => {
                                  const nextNew = (vals ?? []).map((v) => String(v)).filter(Boolean)
                                  setLinkRoleSelectedIds(nextNew)
                                  const merged = Array.from(new Set([...linkedCharacterIds, ...nextNew]))
                                  void (async () => {
                                    await onUpdatePromptActors(merged)
                                    setLinkRoleOpen(false)
                                    setLinkRoleSelectedIds([])
                                  })()
                                }}
                              />
                            </div>
                          </Modal>

                          <Modal
                            title="关联场景"
                            open={linkSceneOpen}
                            onCancel={() => setLinkSceneOpen(false)}
                            footer={null}
                            destroyOnClose
                            width={560}
                          >
                            <div className="space-y-2">
                              <div className="text-xs text-gray-500">来源：当前项目场景（选择后立即保存）</div>
                              <Select
                                className="w-full"
                                placeholder="选择要关联到当前分镜的场景"
                                value={linkedSceneId ?? undefined}
                                loading={linkSceneLoading}
                                disabled={promptAssetsUpdating}
                                options={projectSceneOptions}
                                optionFilterProp="searchLabel"
                                showSearch
                                filterOption={(input: string, option?: any) =>
                                  String(option?.searchLabel ?? '').toLowerCase().includes(input.toLowerCase())
                                }
                                onChange={(v: string) => {
                                  void (async () => {
                                    await onUpdatePromptScene(v)
                                    setLinkSceneOpen(false)
                                  })()
                                }}
                              />
                            </div>
                          </Modal>

                          <Modal
                            title="关联道具"
                            open={linkPropOpen}
                            onCancel={() => setLinkPropOpen(false)}
                            footer={null}
                            destroyOnClose
                            width={560}
                          >
                            <div className="space-y-2">
                              <div className="text-xs text-gray-500">来源：当前项目道具（选择后立即保存；已关联的不可重复选择）</div>
                              <Select
                                mode="multiple"
                                className="w-full"
                                placeholder="选择要关联到当前分镜的道具"
                                value={linkPropSelectedIds}
                                loading={linkPropLoading}
                                disabled={promptAssetsUpdating}
                                options={projectPropOptions}
                                optionFilterProp="searchLabel"
                                showSearch
                                filterOption={(input: string, option?: any) =>
                                  String(option?.searchLabel ?? '').toLowerCase().includes(input.toLowerCase())
                                }
                                onChange={(vals: Array<string | number>) => {
                                  const nextNew = (vals ?? []).map((v) => String(v)).filter(Boolean)
                                  setLinkPropSelectedIds(nextNew)
                                  const merged = Array.from(new Set([...linkedPropIds, ...nextNew]))
                                  void (async () => {
                                    await onUpdatePromptProps(merged)
                                    setLinkPropOpen(false)
                                    setLinkPropSelectedIds([])
                                  })()
                                }}
                              />
                            </div>
                          </Modal>

                          <Modal
                            title="关联服装"
                            open={linkCostumeOpen}
                            onCancel={() => setLinkCostumeOpen(false)}
                            footer={null}
                            destroyOnClose
                            width={560}
                          >
                            <div className="space-y-2">
                              <div className="text-xs text-gray-500">来源：当前项目服装（选择后立即保存；已关联的不可重复选择）</div>
                              <Select
                                mode="multiple"
                                className="w-full"
                                placeholder="选择要关联到当前分镜的服装"
                                value={linkCostumeSelectedIds}
                                loading={linkCostumeLoading}
                                disabled={promptAssetsUpdating}
                                options={projectCostumeOptions}
                                optionFilterProp="searchLabel"
                                showSearch
                                filterOption={(input: string, option?: any) =>
                                  String(option?.searchLabel ?? '').toLowerCase().includes(input.toLowerCase())
                                }
                                onChange={(vals: Array<string | number>) => {
                                  const nextNew = (vals ?? []).map((v) => String(v)).filter(Boolean)
                                  setLinkCostumeSelectedIds(nextNew)
                                  const merged = Array.from(new Set([...linkedCostumeIds, ...nextNew]))
                                  void (async () => {
                                    await onUpdatePromptCostumes(merged)
                                    setLinkCostumeOpen(false)
                                    setLinkCostumeSelectedIds([])
                                  })()
                                }}
                              />
                            </div>
                          </Modal>
                        </Modal>
                      </div>
                    )
                  })}
                </div>
              ),
            },
            ...(showAvTab ? [{
              key: 'av',
              label: '音视频控制',
              children: (
                <div>
                  <div className="cs-group">
                    <div className="cs-group-title">
                      <CustomerServiceOutlined /> 配乐
                    </div>
                    <div className="space-y-3">
                      <Radio.Group
                        value={audioMode}
                        onChange={(e) => setAudioMode(e.target.value)}
                        options={[
                          { value: 'none', label: '无' },
                          { value: 'prompt', label: '提示词' },
                          { value: 'upload', label: '上传音频' },
                        ]}
                      />
                      {audioMode === 'prompt' && <TextArea rows={3} placeholder="配乐提示词（支持多版本）…" />}
                      {audioMode === 'upload' && (
                        <Button block icon={<UploadOutlined />}>
                          上传音频
                        </Button>
                      )}
                    </div>
                  </div>

                  <div className="cs-group">
                    <div className="cs-group-title">
                      <SoundOutlined /> 音效
                    </div>
                    <div className="space-y-3">
                      <Button block icon={<UploadOutlined />}>
                        添加一条音效（Mock）
                      </Button>
                    </div>
                  </div>

                  <div className="cs-group">
                    <div className="cs-group-title">
                      <SettingOutlined /> 开关
                    </div>
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm">关闭配乐</span>
                        <Switch />
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm">关闭对白</span>
                        <Switch />
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm">智能对口型</span>
                        <Switch />
                      </div>
                    </div>
                  </div>
                </div>
              ),
            }] : []),
            {
              key: 'gen_ref',
              label: '生成与参考',
              children: (
                <div>
                  <div className="cs-group">
                    <div className="cs-group-title">
                      <LinkOutlined /> 参考
                    </div>
                    <Select
                      mode="multiple"
                      placeholder="按已有关键帧类型选择"
                      className="w-full"
                      value={refImageType}
                      onChange={setRefImageType}
                      options={refFrameTypeOptions}
                    />
                  </div>

                  {showGenRefParams && (
                    <div className="cs-group">
                      <div className="cs-group-title">
                        <ToolOutlined /> 参数
                      </div>
                      <Space direction="vertical" className="w-full" size="small">
                        <Select
                          size="small"
                          placeholder="模型选择"
                          options={[
                            { value: 'model_a', label: '模型 A（写实）' },
                            { value: 'model_b', label: '模型 B（风格化）' },
                          ]}
                        />
                        <div className="flex items-center justify-between">
                          <span className="text-sm">ControlNet（深度/骨骼）</span>
                          <Switch checked={useBoneDepth} onChange={setUseBoneDepth} />
                        </div>
                        <Slider min={3} max={12} defaultValue={5} />
                      </Space>
                    </div>
                  )}

                  <div className="cs-group">
                    <div className="cs-group-title">
                      <ThunderboltOutlined /> 生成
                    </div>
                    <Space wrap>
                      <Button type="primary" icon={<VideoCameraOutlined />} loading={videoPromptPreviewSubmitting || videoTaskPolling} onClick={() => void openVideoPromptPreview()}>
                        生成视频
                      </Button>
                      {videoTaskStatus ? <span className="text-xs text-gray-500">任务状态：{videoTaskStatus}</span> : null}
                    </Space>
                  </div>

                  <div className="cs-group">
                    <div className="cs-group-title">
                      <VideoCameraOutlined /> 已生成视频
                    </div>
                    {generatedVideos.length === 0 ? (
                      <div className="text-xs text-gray-400">当前分镜暂无已生成视频</div>
                    ) : (
                      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
                        {generatedVideos.map((item, idx) => (
                          <div key={`${item.linkId}-${item.fileId}`} className="border rounded p-2">
                            <video
                              src={item.url}
                              className="w-full h-20 rounded object-cover bg-black"
                              preload="metadata"
                              muted
                              onClick={() => onSelectPreviewVideo(item.fileId)}
                              style={{ cursor: 'pointer' }}
                            />
                            <div className="mt-2 flex items-center justify-between gap-2">
                              <span className="text-xs text-gray-500">视频 {idx + 1}</span>
                              <Tooltip title="下载视频">
                                <Button
                                  size="small"
                                  icon={<DownloadOutlined />}
                                  onClick={() => {
                                    if (!item.url) return
                                    window.open(item.url, '_blank', 'noopener,noreferrer')
                                  }}
                                />
                              </Tooltip>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {showGenRefVersions && (
                    <div className="cs-group">
                      <div className="cs-group-title">
                        <AppstoreOutlined /> 版本
                      </div>
                      <Tabs
                        type="card"
                        size="small"
                        activeKey={imageVersion}
                        onChange={setImageVersion}
                        items={[
                          { key: 'v1', label: 'v1' },
                          { key: 'v2', label: 'v2' },
                          { key: 'v3', label: 'v3' },
                        ]}
                      />
                    </div>
                  )}
                </div>
              ),
            },
          ]}
        />

        <Modal
          title={`${frameLabel[keyframePromptPreviewFrameType]}图片生成提示词预览`}
          open={keyframePromptPreviewOpen}
          onCancel={() => {
            if (keyframePromptActionLoading) return
            setKeyframePromptPreviewOpen(false)
          }}
          footer={(
            <div className="flex items-center justify-between">
              <Button
                loading={keyframePromptActionLoading}
                onClick={() => void regenerateKeyframePrompt()}
              >
                {getPromptFromDetailByType(keyframePromptPreviewFrameType).trim() ? '重新生成提示词' : '生成提示词'}
              </Button>
              <Space>
                <Button
                  loading={keyframePromptActionLoading}
                  onClick={() => {
                    if (keyframePromptActionLoading) return
                    setKeyframePromptPreviewOpen(false)
                  }}
                >
                  取消
                </Button>
                <Button type="primary" loading={keyframePromptActionLoading} onClick={() => void confirmGenerateKeyframeWithPrompt()}>
                  生成
                </Button>
              </Space>
            </div>
          )}
          destroyOnClose
          width={900}
        >
          {keyframePromptPreviewLoading ? (
            <div className="py-8 text-center">
              <Spin />
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <div className="text-xs text-gray-500 mb-2">关联图片（参考图）</div>
                {keyframePromptPreviewRefFileIds.length === 0 ? (
                  <div className="text-xs text-gray-400">暂无关联图片</div>
                ) : (
                  <div className="flex gap-2 overflow-x-auto pb-1">
                    <Image.PreviewGroup>
                      {keyframePromptPreviewRefFileIds.map((fid) => (
                        <Tooltip key={fid} title={shotLinkedAssetNameByFileId.get(fid) ?? fid}>
                          <Image
                            width={72}
                            height={72}
                            style={{ objectFit: 'cover', borderRadius: 8 }}
                            src={buildFileDownloadUrl(fid)}
                          />
                        </Tooltip>
                      ))}
                    </Image.PreviewGroup>
                  </div>
                )}
              </div>
              <div>
                <div className="text-xs text-gray-500 mb-2">提示词（可编辑）</div>
                <Input.TextArea
                  rows={10}
                  value={keyframePromptPreviewDraft}
                  onChange={(e) => setKeyframePromptPreviewDraft(e.target.value)}
                  placeholder="请输入提示词…"
                  disabled={keyframePromptActionLoading || shotRenderPromptLoading}
                />
              </div>
            </div>
          )}
        </Modal>

        <Modal
          title="视频生成提示词预览"
          open={videoPromptPreviewOpen}
          onCancel={() => {
            if (videoPromptPreviewSubmitting) return
            setVideoPromptPreviewOpen(false)
          }}
          okText="生成"
          cancelText="取消"
          onOk={() => void submitVideoGeneration()}
          confirmLoading={videoPromptPreviewSubmitting}
          width={900}
          destroyOnClose
        >
          {videoPromptPreviewLoading ? (
            <div className="py-8 text-center">
              <Spin />
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <div className="text-xs text-gray-500 mb-2">关联图片（参考图）</div>
                {videoPromptPreviewImages.length === 0 ? (
                  <div className="text-xs text-gray-400">暂无关联图片</div>
                ) : (
                  <div className="flex gap-2 overflow-x-auto pb-1">
                    <Image.PreviewGroup>
                      {videoPromptPreviewImages.map((fid) => (
                        <Image
                          key={fid}
                          width={72}
                          height={72}
                          style={{ objectFit: 'cover', borderRadius: 8 }}
                          src={buildFileDownloadUrl(fid)}
                        />
                      ))}
                    </Image.PreviewGroup>
                  </div>
                )}
              </div>
              <div>
                <div className="text-xs text-gray-500 mb-2">提示词（可编辑）</div>
                <Input.TextArea
                  rows={10}
                  value={videoPromptPreviewDraft}
                  onChange={(e) => setVideoPromptPreviewDraft(e.target.value)}
                  placeholder="请输入视频提示词…"
                  disabled={videoPromptPreviewSubmitting}
                />
              </div>
            </div>
          )}
        </Modal>
      </div>
    </div>
  )
}
