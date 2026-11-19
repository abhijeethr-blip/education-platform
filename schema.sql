-- Dedicated schema avoids collisions with pre-existing public.institutions table.
CREATE SCHEMA IF NOT EXISTS edu;
CREATE TABLE IF NOT EXISTS edu.institutions (
 id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, website TEXT NOT NULL UNIQUE,
 city TEXT, state TEXT, country TEXT DEFAULT 'India', attributes JSONB NOT NULL DEFAULT '{}',
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS edu.source_pages (
 id BIGSERIAL PRIMARY KEY, institution_id BIGINT NOT NULL REFERENCES edu.institutions(id) ON DELETE CASCADE,
 url TEXT NOT NULL, fetched_at TIMESTAMPTZ, status TEXT NOT NULL,
 title TEXT, extracted_text TEXT, metadata JSONB NOT NULL DEFAULT '{}',
 UNIQUE(institution_id,url));
CREATE TABLE IF NOT EXISTS edu.facts (
 id BIGSERIAL PRIMARY KEY, institution_id BIGINT NOT NULL REFERENCES edu.institutions(id) ON DELETE CASCADE,
 field_key TEXT NOT NULL, field_value JSONB NOT NULL,
 source_page_id BIGINT NOT NULL REFERENCES edu.source_pages(id) ON DELETE CASCADE,
 review_status TEXT NOT NULL DEFAULT 'unverified' CHECK (review_status IN ('unverified','verified','rejected')),
 extracted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(institution_id,field_key,source_page_id));
CREATE INDEX IF NOT EXISTS edu_facts_field_idx ON edu.facts(field_key);
CREATE INDEX IF NOT EXISTS edu_institutions_attr_idx ON edu.institutions USING GIN(attributes);
