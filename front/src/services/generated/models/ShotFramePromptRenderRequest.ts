/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ShotFrameType } from './ShotFrameType';
import type { ShotLinkedAssetItem } from './ShotLinkedAssetItem';
/**
 * 镜头分镜帧提示词渲染请求体。
 */
export type ShotFramePromptRenderRequest = {
    /**
     * first | last | key
     */
    frame_type: ShotFrameType;
    /**
     * 保留字段，当前渲染接口不使用；用于与前端调用参数保持一致。
     */
    model_id?: (string | null);
    /**
     * 可选提示词。为空时由后端基于分镜数据自动生成；非空时将参考图说明拼接后直接返回。
     */
    prompt?: (string | null);
    /**
     * 参考资产条目列表（可多张，顺序有效）。后端会使用 item.file_id 作为参考图；无效条目会被跳过。
     */
    images?: Array<ShotLinkedAssetItem>;
};

