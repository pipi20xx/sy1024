export interface CollectionItem {
  id: string
  name: string
}

export interface Collection {
  name: string
  collection_name?: string
  overview: string
  items?: string[]
  movies?: CollectionItem[]
  series?: CollectionItem[]
  movie_count?: number
  series_count?: number
  poster_path?: string
  backdrop_path?: string
  filename: string
  item_type?: string
}
