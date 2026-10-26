"""Copy the publishable source allowlist; never copy private runtime evidence."""
import json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sync():
 public=ROOT/'publish';dest=public/'crawler';dest.mkdir(exist_ok=True)
 for name in ('README.md','requirements.txt','run.sh'):shutil.copy2(ROOT/name,dest/name)
 for name in ('radar','scripts','tests','config','docs'):
  shutil.copytree(ROOT/name,dest/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store'))
 legacy=dest/'config/legacy_seeds.json';rows=json.loads(legacy.read_text())
 for row in rows:
  if isinstance(row,dict) and row.get('imported_from'):row['imported_from']='旧周报：'+Path(row['imported_from']).name
 legacy.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 for name in ('index.html','style.css','app.js','sources.js','sop.html','sop.css','sop.js','sop-state.js','sop-data.js','sop-offline.html'):
  (dest/'publish').mkdir(exist_ok=True);shutil.copy2(public/name,dest/'publish'/name)
 invalid=[]
 for path in dest.rglob('*'):
  if path.is_file() and path.suffix in ('.md','.json','.py','.js','.cjs','.html','.css','.yml','.txt','.sh'):
   text=path.read_text(errors='replace')
   if str(Path.home())+'/' in text or str(Path('/private')/'var'/'folders')+'/' in text:invalid.append(str(path.relative_to(public)))
 if invalid:raise ValueError('Private paths in public source: '+repr(invalid))
 return {'sourceCopied':True,'privateDataCopied':False}
if __name__=='__main__':print(json.dumps(sync()))
