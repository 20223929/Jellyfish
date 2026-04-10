/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ShotAssetsOverviewRead } from './ShotAssetsOverviewRead';
import type { ShotDialogLineRead } from './ShotDialogLineRead';
import type { ShotExtractedDialogueCandidateRead } from './ShotExtractedDialogueCandidateRead';
import type { ShotRead } from './ShotRead';
/**
 * 分镜准备页聚合状态。
 */
export type ShotPreparationStateRead = {
    /**
     * 当前镜头最新状态
     */
    shot: ShotRead;
    /**
     * 资产确认区聚合状态
     */
    assets_overview: ShotAssetsOverviewRead;
    /**
     * 当前待处理/已存在的对白候选
     */
    dialogue_candidates?: Array<ShotExtractedDialogueCandidateRead>;
    /**
     * 当前已保存的对白行
     */
    saved_dialogue_lines?: Array<ShotDialogLineRead>;
    /**
     * 当前仍待确认的总数量（资产 + 对白）
     */
    pending_confirm_count: number;
    /**
     * 当前镜头是否已完成准备，可进入后续生成
     */
    ready_for_generation: boolean;
};

