/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 道具信息缺失分析请求。
 */
export type PropInfoAnalysisRequest = {
    /**
     * 原文道具上下文（可为空；用于提供额外背景，帮助判断缺失信息）
     */
    prop_context?: (string | null);
    /**
     * 原文道具描述
     */
    prop_description: string;
};

