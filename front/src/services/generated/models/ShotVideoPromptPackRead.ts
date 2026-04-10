/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ShotPromptAssetRef } from './ShotPromptAssetRef';
import type { ShotPromptCameraInfo } from './ShotPromptCameraInfo';
/**
 * 视频提示词渲染前的标准上下文包。
 */
export type ShotVideoPromptPackRead = {
    /**
     * 镜头 ID
     */
    shot_id: string;
    /**
     * 镜头标题
     */
    title?: string;
    /**
     * 剧本摘录
     */
    script_excerpt?: string;
    /**
     * 动作/场景要点
     */
    action_beats?: Array<string>;
    /**
     * 对白摘要
     */
    dialogue_summary?: string;
    /**
     * 角色引用
     */
    characters?: Array<ShotPromptAssetRef>;
    /**
     * 场景引用
     */
    scene?: (ShotPromptAssetRef | null);
    /**
     * 道具引用
     */
    props?: Array<ShotPromptAssetRef>;
    /**
     * 服装引用
     */
    costumes?: Array<ShotPromptAssetRef>;
    /**
     * 镜头语言
     */
    camera?: ShotPromptCameraInfo;
    /**
     * 氛围描述
     */
    atmosphere?: string;
    /**
     * 项目视觉风格
     */
    visual_style?: string;
    /**
     * 项目题材/风格
     */
    style?: string;
    /**
     * 默认负面提示词
     */
    negative_prompt?: string;
};

