-- Re-runnable, no reset/delete. Apply with the Supabase SQL editor or migrations CLI.
create table if not exists public.rescue_workspace (
 id text primary key check(id='synthetic-demo'), revision bigint not null default 1, document jsonb not null,
 updated_at timestamptz not null default now(), check(document->>'synthetic'='true')
);
create table if not exists public.rescue_ai_jobs (
 id text primary key, payload jsonb not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.rescue_ai_budget (day date primary key, used integer not null default 0 check(used>=0));
alter table public.rescue_workspace enable row level security;
alter table public.rescue_ai_jobs enable row level security;
alter table public.rescue_ai_budget enable row level security;
revoke all on public.rescue_workspace,public.rescue_ai_jobs,public.rescue_ai_budget from public,anon,authenticated;
grant all on public.rescue_workspace,public.rescue_ai_jobs,public.rescue_ai_budget to service_role;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types) values('rescue-private','rescue-private',false,3145728,array['image/png','image/jpeg','audio/wav','audio/mpeg','video/mp4']) on conflict(id) do update set public=false,file_size_limit=3145728,allowed_mime_types=excluded.allowed_mime_types;
-- Restrictive fence also prevents unrelated broad policies from exposing this bucket.
do $$ begin
 if not exists(select 1 from pg_policies where schemaname='storage' and tablename='objects' and policyname='rescue_private_server_only') then
  create policy rescue_private_server_only on storage.objects as restrictive for all to anon,authenticated using(bucket_id <> 'rescue-private') with check(bucket_id <> 'rescue-private');
 end if;
end $$;
create or replace function public.rescue_init(p_document jsonb) returns jsonb language plpgsql security definer set search_path=public as $$
declare w rescue_workspace;
begin
 if p_document->>'synthetic' is distinct from 'true' then raise exception 'synthetic required';end if;
 insert into rescue_workspace(id,document) values('synthetic-demo',p_document) on conflict(id) do nothing;
 select * into w from rescue_workspace where id='synthetic-demo';return jsonb_build_object('revision',w.revision,'document',w.document);
end $$;
create or replace function public.rescue_cas(p_revision bigint,p_document jsonb) returns jsonb language plpgsql security definer set search_path=public as $$
declare w rescue_workspace;
begin
 if p_document->>'synthetic' is distinct from 'true' then raise exception 'synthetic required';end if;
 update rescue_workspace set document=p_document,revision=revision+1,updated_at=now() where id='synthetic-demo' and revision=p_revision returning * into w;
 if not found then raise exception using errcode='P0001',message='REVISION_CONFLICT';end if;
 return jsonb_build_object('revision',w.revision,'document',w.document);
end $$;
create or replace function public.rescue_create_job(p_job jsonb,p_limit integer) returns jsonb language plpgsql security definer set search_path=public as $$
declare used_count integer;
begin
 if p_limit<1 or p_limit>1000 or p_job->>'status' is distinct from 'queued' or p_job->>'synthetic' is distinct from 'true' then raise exception 'invalid job';end if;
 insert into rescue_ai_budget(day,used) values((now() at time zone 'UTC')::date,0) on conflict(day) do nothing;
 update rescue_ai_budget set used=used+1 where day=(now() at time zone 'UTC')::date and used<p_limit returning used into used_count;
 if not found then raise exception using errcode='P0001',message='AI_DAILY_LIMIT';end if;
 insert into rescue_ai_jobs(id,payload) values(p_job->>'id',p_job);return p_job;
end $$;
create or replace function public.rescue_claim_job(p_id text,p_hash text) returns jsonb language plpgsql security definer set search_path=public as $$
declare j rescue_ai_jobs;
begin
 update rescue_ai_jobs set payload=payload||jsonb_build_object('status','running','updated_at',now(),'execution',(payload->'execution')||jsonb_build_object('started_at',now())),updated_at=now() where id=p_id and payload->>'status'='queued' and payload->'execution'->>'input_sha256'=p_hash returning * into j;
 if not found then return null;end if;return j.payload;
end $$;
create or replace function public.rescue_finish_job(p_id text,p_payload jsonb) returns jsonb language plpgsql security definer set search_path=public as $$
declare j rescue_ai_jobs;
begin
 if p_payload->>'status' not in ('ready','failed') then raise exception 'invalid status';end if;
 update rescue_ai_jobs set payload=payload||p_payload||jsonb_build_object('updated_at',now()),updated_at=now() where id=p_id and payload->>'status' in ('queued','running') returning * into j;
 return j.payload;
end $$;
create or replace function public.rescue_get_job(p_id text) returns jsonb language plpgsql security definer set search_path=public as $$
declare j rescue_ai_jobs;
begin
 update rescue_ai_jobs set payload=payload||jsonb_build_object('status','failed','error','분석 작업 시간초과: 원문을 보존했습니다.','updated_at',now()),updated_at=now() where id=p_id and payload->>'status' in ('queued','running') and updated_at<now()-interval '10 minutes';
 select * into j from rescue_ai_jobs where id=p_id;return j.payload;
end $$;
create or replace function public.rescue_confirm_job(p_id text,p_revision bigint,p_document jsonb,p_result jsonb) returns jsonb language plpgsql security definer set search_path=public as $$
declare j rescue_ai_jobs; w rescue_workspace;
begin
 select * into j from rescue_ai_jobs where id=p_id for update;
 if not found then raise exception 'JOB_NOT_FOUND';end if;
 if j.payload->>'status'='confirmed' then return j.payload->'confirmation';end if;
 if j.payload->>'status' is distinct from 'ready' then raise exception 'JOB_NOT_READY';end if;
 if p_document->>'synthetic' is distinct from 'true' then raise exception 'synthetic required';end if;
 update rescue_workspace set document=p_document,revision=revision+1,updated_at=now() where id='synthetic-demo' and revision=p_revision returning * into w;
 if not found then raise exception using errcode='P0001',message='REVISION_CONFLICT';end if;
 update rescue_ai_jobs set payload=payload||jsonb_build_object('status','confirmed','confirmation',p_result,'updated_at',now()),updated_at=now() where id=p_id;
 return p_result;
end $$;
revoke all on function public.rescue_init(jsonb),public.rescue_cas(bigint,jsonb),public.rescue_create_job(jsonb,integer),public.rescue_claim_job(text,text),public.rescue_finish_job(text,jsonb),public.rescue_get_job(text),public.rescue_confirm_job(text,bigint,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.rescue_init(jsonb),public.rescue_cas(bigint,jsonb),public.rescue_create_job(jsonb,integer),public.rescue_claim_job(text,text),public.rescue_finish_job(text,jsonb),public.rescue_get_job(text),public.rescue_confirm_job(text,bigint,jsonb,jsonb) to service_role;
