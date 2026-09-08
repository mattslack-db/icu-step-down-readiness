import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import type { UseQueryOptions, UseSuspenseQueryOptions } from "@tanstack/react-query";
export class ApiError extends Error {
    status: number;
    statusText: string;
    body: unknown;
    constructor(status: number, statusText: string, body: unknown){
        super(`HTTP ${status}: ${statusText}`);
        this.name = "ApiError";
        this.status = status;
        this.statusText = statusText;
        this.body = body;
    }
}
export interface AnalyticsResponse {
    avg_los_by_band: Record<string, number>;
    band_distribution: BandCount[];
    feature_importance: FeatureImportanceItem[];
    generated_at: string;
    total_census: number;
    vasopressor_rate: number;
    vent_rate: number;
}
export interface BandCount {
    band: string;
    count: number;
    pct: number;
}
export interface CensusPatient {
    age: number;
    band: string;
    icustay_id: string;
    los: number;
    on_vasopressors: boolean;
    on_ventilator: boolean;
    readiness_index: number;
    readiness_score: number;
    subject_id: string;
    top_factors: FactorOut[];
}
export interface CensusResponse {
    generated_at: string;
    patients: CensusPatient[];
    total: number;
}
export interface ComplexValue {
    display?: string | null;
    primary?: boolean | null;
    ref?: string | null;
    type?: string | null;
    value?: string | null;
}
export interface FactorOut {
    direction: string;
    magnitude: number;
    name: string;
}
export interface FeatureImportanceItem {
    feature: string;
    importance: number;
}
export interface HTTPValidationError {
    detail?: ValidationError[];
}
export interface Name {
    family_name?: string | null;
    given_name?: string | null;
}
export interface PatientDetail {
    band: string;
    factors: FactorOut[];
    features: PatientFeatures;
    lactate_note: string | null;
    narrative: string;
    readiness_index: number;
    readiness_score: number;
    vitals: VitalPoint[];
}
export interface PatientFeatures {
    age: number;
    dbp_mean: number | null;
    gcs_last: number | null;
    hr_mean: number | null;
    icustay_id: string;
    lactate_last: number | null;
    los: number;
    on_vasopressors: boolean;
    on_ventilator: boolean;
    rr_mean: number | null;
    sbp_mean: number | null;
    spo2_mean: number | null;
    spo2_min: number | null;
    subject_id: string;
    temp_c_mean: number | null;
}
export interface User {
    active?: boolean | null;
    display_name?: string | null;
    emails?: ComplexValue[] | null;
    entitlements?: ComplexValue[] | null;
    external_id?: string | null;
    groups?: ComplexValue[] | null;
    id?: string | null;
    name?: Name | null;
    roles?: ComplexValue[] | null;
    schemas?: UserSchema[] | null;
    user_name?: string | null;
}
export const UserSchema = {
    "urn:ietf:params:scim:schemas:core:2.0:User": "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:workspace:2.0:User": "urn:ietf:params:scim:schemas:extension:workspace:2.0:User"
} as const;
export type UserSchema = typeof UserSchema[keyof typeof UserSchema];
export interface ValidationError {
    ctx?: Record<string, unknown>;
    input?: unknown;
    loc: (string | number)[];
    msg: string;
    type: string;
}
export interface VersionOut {
    version: string;
}
export interface VitalPoint {
    charttime: string;
    value: number;
    vital_name: string;
}
export const getAnalytics = async (options?: RequestInit): Promise<{
    data: AnalyticsResponse;
}> =>{
    const res = await fetch("/api/analytics", {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const getAnalyticsKey = ()=>{
    return [
        "/api/analytics"
    ] as const;
};
export function useGetAnalytics<TData = {
    data: AnalyticsResponse;
}>(options?: {
    query?: Omit<UseQueryOptions<{
        data: AnalyticsResponse;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: getAnalyticsKey(),
        queryFn: ()=>getAnalytics(),
        ...options?.query
    });
}
export function useGetAnalyticsSuspense<TData = {
    data: AnalyticsResponse;
}>(options?: {
    query?: Omit<UseSuspenseQueryOptions<{
        data: AnalyticsResponse;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: getAnalyticsKey(),
        queryFn: ()=>getAnalytics(),
        ...options?.query
    });
}
export const getCensus = async (options?: RequestInit): Promise<{
    data: CensusResponse;
}> =>{
    const res = await fetch("/api/census", {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const getCensusKey = ()=>{
    return [
        "/api/census"
    ] as const;
};
export function useGetCensus<TData = {
    data: CensusResponse;
}>(options?: {
    query?: Omit<UseQueryOptions<{
        data: CensusResponse;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: getCensusKey(),
        queryFn: ()=>getCensus(),
        ...options?.query
    });
}
export function useGetCensusSuspense<TData = {
    data: CensusResponse;
}>(options?: {
    query?: Omit<UseSuspenseQueryOptions<{
        data: CensusResponse;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: getCensusKey(),
        queryFn: ()=>getCensus(),
        ...options?.query
    });
}
export interface CurrentUserParams {
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const currentUser = async (params?: CurrentUserParams, options?: RequestInit): Promise<{
    data: User;
}> =>{
    const res = await fetch("/api/current-user", {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const currentUserKey = (params?: CurrentUserParams)=>{
    return [
        "/api/current-user",
        params
    ] as const;
};
export function useCurrentUser<TData = {
    data: User;
}>(options?: {
    params?: CurrentUserParams;
    query?: Omit<UseQueryOptions<{
        data: User;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: currentUserKey(options?.params),
        queryFn: ()=>currentUser(options?.params),
        ...options?.query
    });
}
export function useCurrentUserSuspense<TData = {
    data: User;
}>(options?: {
    params?: CurrentUserParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: User;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: currentUserKey(options?.params),
        queryFn: ()=>currentUser(options?.params),
        ...options?.query
    });
}
export interface GetPatientParams {
    icustay_id: string;
}
export const getPatient = async (params: GetPatientParams, options?: RequestInit): Promise<{
    data: PatientDetail;
}> =>{
    const res = await fetch(`/api/patients/${params.icustay_id}`, {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const getPatientKey = (params?: GetPatientParams)=>{
    return [
        "/api/patients/{icustay_id}",
        params
    ] as const;
};
export function useGetPatient<TData = {
    data: PatientDetail;
}>(options: {
    params: GetPatientParams;
    query?: Omit<UseQueryOptions<{
        data: PatientDetail;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: getPatientKey(options.params),
        queryFn: ()=>getPatient(options.params),
        ...options?.query
    });
}
export function useGetPatientSuspense<TData = {
    data: PatientDetail;
}>(options: {
    params: GetPatientParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: PatientDetail;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: getPatientKey(options.params),
        queryFn: ()=>getPatient(options.params),
        ...options?.query
    });
}
export const version = async (options?: RequestInit): Promise<{
    data: VersionOut;
}> =>{
    const res = await fetch("/api/version", {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const versionKey = ()=>{
    return [
        "/api/version"
    ] as const;
};
export function useVersion<TData = {
    data: VersionOut;
}>(options?: {
    query?: Omit<UseQueryOptions<{
        data: VersionOut;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: versionKey(),
        queryFn: ()=>version(),
        ...options?.query
    });
}
export function useVersionSuspense<TData = {
    data: VersionOut;
}>(options?: {
    query?: Omit<UseSuspenseQueryOptions<{
        data: VersionOut;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: versionKey(),
        queryFn: ()=>version(),
        ...options?.query
    });
}
