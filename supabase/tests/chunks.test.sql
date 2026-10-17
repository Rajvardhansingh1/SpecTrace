begin;
select plan(8);

select has_table('public', 'chunks', 'chunks table exists');
select has_column('public', 'runs', 'owner_hash', 'runs are owner scoped');
select ok(
  (select relrowsecurity from pg_class where oid = 'public.chunks'::regclass),
  'RLS is enabled on chunks'
);
select ok(
  exists (select 1 from pg_extension where extname = 'vector'),
  'the vector extension is installed'
);

insert into public.runs (id, status, label_a, label_b, files_a, files_b, owner_hash)
values ('00000000-0000-4000-8000-000000000001', 'done', 'a', 'b', '{}', '{}', 'owner');

select lives_ok(
  $$insert into public.chunks (run_id, version, key, kind, name, file, line_start, line_end, ordinal, text, text_hash, embedding, embedding_model)
    values ('00000000-0000-4000-8000-000000000001', 'a', 'schema:Pet', 'schema', 'Pet', 'o.yaml', 1, 2, 0, 't', 'h', '[1,0,0]', 'm')$$,
  'a chunk with an embedding can be stored'
);
select throws_ok(
  $$insert into public.chunks (run_id, version, key, kind, name, file, line_start, line_end, ordinal, text, text_hash)
    values ('00000000-0000-4000-8000-000000000001', 'c', 'k', 'k', 'n', 'f', 1, 2, 0, 't', 'h')$$,
  '23514', null, 'an unknown version is rejected'
);

set local role anon;
select throws_ok('select 1 from public.chunks', '42501', null, 'anon cannot read chunks');
reset role;

delete from public.runs where id = '00000000-0000-4000-8000-000000000001';
select is(
  (select count(*)::int from public.chunks where run_id = '00000000-0000-4000-8000-000000000001'),
  0,
  'deleting a run deletes its chunks'
);
select * from finish();
rollback;
