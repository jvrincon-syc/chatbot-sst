UPDATE indexing_profiles
   SET compatibility_status = 'compatibility_not_proven',
       document_enabled = false,
       query_enabled = false
 WHERE compatibility_status <> 'verified';

-- Backfill legacy retirado (refactor pure-platform, esta rama). Los dos INSERT
-- fabricaban filas ``legacy-*`` en chunk_bundles/embedding_bundles desde
-- indexing_normalized_documents en cada ``prepare``; sin project_id violaban la
-- columna NOT NULL de la BD viva, y re-contaminaban las tablas tras cada hard
-- reset. La plataforma pura no arranca desde bundles legacy: chunk/embedding se
-- registran por su pipeline real. Se conserva solo el UPDATE de guarda de perfiles.

