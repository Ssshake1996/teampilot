export interface LoginRequest { username: string; password: string }
export interface ReviewRequest { draftId: string; payloadHash: string }
export interface DraftRequest { draftId: string }
export interface ReadRequest { resource: 'projects' | 'drafts'; page: number }
export interface ConnectionStatus { connected: boolean; username: string; baseUrl: string; webUrl: string }
export interface JsonResponse { json: string }
export interface ReviewResponse { approved: boolean; draftId: string }
