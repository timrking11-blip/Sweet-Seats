-- Public on-sale time as the source states it (SS-DATA-0.1 SourceEventRecord:
-- publication/on_sale/presale times). Stored as the source's zoned ISO string, like
-- the other observation timestamps, and validated as a timestamp. Null means unknown.
alter table public.source_event_records add column onsale_at text
  check (onsale_at is null or onsale_at::timestamptz is not null);
