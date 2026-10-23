
import { api } from './client';

export interface GeneratePosterRequest {
    collection_id?: string;
    item_ids?: string[];
    movie_ids?: string[];
    series_ids?: string[];
    titles_map?: Record<string, string[]>;
    style_type: string;
    title_zh?: string;
    title_en?: string;
    show_zh: boolean;
    show_en: boolean;
    font_zh: string;
    font_en: string;
    zh_font_size_ratio: number;
    en_font_size_ratio: number;
    offset_x: number;
    offset_y: number;
    resolution_scale: number;
    seed?: number;
    return_layers: boolean;
}

export interface PosterLayers {
    base: string; // base64
    text: string; // base64
}

export interface FontsResponse {
    fonts: string[];
}

export interface BatchGenerateRequest {
    collection_filenames: string[];
    collection_names_str?: string;
    style_type: string;
    show_zh: boolean;
    show_en: boolean;
    font_zh: string;
    font_en: string;
    zh_font_size_ratio: number;
    en_font_size_ratio: number;
    offset_x: number;
    offset_y: number;
    resolution_scale: number;
    seed?: number;
}

export async function generateCollectionPoster(data: GeneratePosterRequest): Promise<string | PosterLayers> {
    return api.post('/api/collection-posters/generate', data);
}

export async function batchGenerateCollectionPosterBg(data: BatchGenerateRequest): Promise<{ message: string; success: boolean }> {
    return api.post('/api/collection-posters/batch-generate-bg', data);
}

export async function getAvailableFonts(): Promise<FontsResponse> {
    return api.get('/api/covers/fonts');
}
