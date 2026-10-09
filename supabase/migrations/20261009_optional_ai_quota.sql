-- Additive/re-runnable replacement; preserves existing jobs, workspace and budget.
create or replace function public.rescue_create_job(p_job jsonb,p_limit integer) returns jsonb language plpgsql security definer set search_path=public as $$
declare used_count integer;
begin
 if jsonb_typeof(p_job) is distinct from 'object'
    or p_job->>'status' is distinct from 'queued'
    or p_job->>'synthetic' is distinct from 'true'
    or coalesce(p_job->>'id','')=''
    or (p_limit is not null and (p_limit<1 or p_limit>1000))
 then raise exception 'invalid job';end if;
 -- NULL deliberately bypasses quota. API maps unset/zero configuration to NULL.
 if p_limit is not null then
  insert into rescue_ai_budget(day,used) values((now() at time zone 'UTC')::date,0) on conflict(day) do nothing;
  update rescue_ai_budget set used=used+1 where day=(now() at time zone 'UTC')::date and used<p_limit returning used into used_count;
  if not found then raise exception using errcode='P0001',message='AI_DAILY_LIMIT';end if;
 end if;
 insert into rescue_ai_jobs(id,payload) values(p_job->>'id',p_job);return p_job;
end $$;
revoke all on function public.rescue_create_job(jsonb,integer) from public,anon,authenticated;
grant execute on function public.rescue_create_job(jsonb,integer) to service_role;
