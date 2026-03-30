/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 服装信息缺失分析请求。
 */
export type CostumeInfoAnalysisRequest = {
    /**
     * 原文服装上下文（可为空；用于提供额外背景，帮助判断缺失信息）
     */
    costume_context?: (string | null);
    /**
     * 原文服装描述
     */
    costume_description: string;
};

