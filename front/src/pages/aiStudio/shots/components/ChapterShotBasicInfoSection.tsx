import { Button, Input } from 'antd'
import { SaveOutlined } from '@ant-design/icons'

type ChapterShotBasicInfoSectionProps = {
  title: string
  scriptExcerpt: string
  saving: boolean
  onTitleChange: (value: string) => void
  onScriptExcerptChange: (value: string) => void
  onSave: () => void
}

export function ChapterShotBasicInfoSection({
  title,
  scriptExcerpt,
  saving,
  onTitleChange,
  onScriptExcerptChange,
  onSave,
}: ChapterShotBasicInfoSectionProps) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm space-y-3">
      <div className="min-w-0">
        <div className="text-sm font-medium text-slate-900">镜头基础信息</div>
        <div className="text-[11px] text-slate-500 mt-1">先确认标题和内容，再继续处理系统提取结果。</div>
      </div>

      <div className="space-y-3">
        <div>
          <div className="text-xs text-gray-600 mb-1">标题</div>
          <Input
            value={title}
            onChange={(e) => onTitleChange(e.target.value)}
            placeholder="标题"
          />
        </div>

        <div>
          <div className="flex items-center justify-between gap-2 mb-1">
            <div className="text-xs text-gray-600">内容 / 剧本摘录</div>
            <Button
              type="primary"
              size="small"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={onSave}
            >
              保存
            </Button>
          </div>
          <Input.TextArea
            value={scriptExcerpt}
            onChange={(e) => onScriptExcerptChange(e.target.value)}
            autoSize={{ minRows: 4, maxRows: 14 }}
            placeholder="剧本摘录"
          />
        </div>
      </div>
    </div>
  )
}
