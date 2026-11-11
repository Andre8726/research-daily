/* Supabase client 2.118.0; only a public client key is used. */
(() => {
  const client = window.supabase.createClient('https://cimiaslbxvmasfhwypqv.supabase.co', 'sb_publishable_-ioP5_ay9BbgeFWyz2UJjQ_n7gt1U8r');
  const note = document.querySelector('#cloud-status');
  const login = document.querySelector('#cloud-login');
  const logout = document.querySelector('#cloud-logout');
  const migrate = document.querySelector('#cloud-import');
  let user = null, pending = {}, busy = false, again = false, ready = false;
  const storageKey = () => user ? 'research-daily-user-' + user.id : 'research-daily-reading-v1';
  const dirtyKey = () => storageKey() + '-pending';
  const valid = value => value && typeof value === 'object' && !Array.isArray(value) ? Object.fromEntries(Object.entries(value).filter(([k,v])=>['unread','pending','read'].includes(v))) : {};
  function read(key) { try { return valid(JSON.parse(localStorage.getItem(key)||'{}')); } catch { return {}; } }
  function cache() { try { localStorage.setItem(storageKey(),JSON.stringify(reading)); localStorage.setItem(dirtyKey(),JSON.stringify(pending)); } catch { note.textContent='本地缓存不可用，请保持联网。'; } }
  function show() { login.hidden=!!user;logout.hidden=!user;migrate.hidden=!user||!Object.keys(read('research-daily-reading-v1')).length; document.querySelectorAll('.read-control select, .pending-actions button').forEach(n=>n.disabled=!!user&&!ready); }
  async function sync() {
    if (!user || !ready) return;
    if (busy) { again=true;return; }
    busy=true;const owner=user.id;
    try {
      const batch={...pending};
      if(Object.keys(batch).length) {
        const {error}=await client.from('reading_states').upsert(Object.entries(batch).map(([paper_id,status])=>({user_id:owner,paper_id,status})),{onConflict:'user_id,paper_id'});
        if(error)throw error;
        if(user?.id!==owner)return;
        for(const [key,value] of Object.entries(batch))if(pending[key]===value)delete pending[key];
      }
      const {data,error}=await client.from('reading_states').select('paper_id,status').eq('user_id',owner);
      if(error)throw error;
      if(user?.id!==owner)return;
      reading={...Object.fromEntries(data.map(r=>[r.paper_id,r.status])),...pending};cache();render();
      note.textContent=Object.keys(pending).length?'有更改待同步':'已登录 · 阅读记录已同步';
    } catch { if(user?.id===owner){cache();note.textContent='云端同步失败，更改已保留；联网后点击重试。';} }
    finally {busy=false;show();if(again){again=false;sync();}}
  }
  window.cloudReadingChanged=(key,value)=>{if(user){if(!ready)return;pending[key]=value;}cache();if(user)sync();};
  window.cloudReadingStorageKey=storageKey;
  window.cloudReadingIsAuthenticated=()=>!!user;
  async function sessionChanged(session) {
    const next=session?.user||null;if(next?.id===user?.id){show();return;}
    user=next;ready=false;pending=read(dirtyKey());reading=read(storageKey());render();show();
    if(user){note.textContent='正在加载云端记录…';ready=true;await sync();}
    else{ready=true;note.textContent='未登录 · 记录仅保存在当前浏览器';show();}
  }
  client.auth.onAuthStateChange((_event,session)=>{setTimeout(()=>sessionChanged(session),0);});
  client.auth.getSession().then(({data,error})=>{if(error){note.textContent='登录状态加载失败，请重试';return;}if(!data.session){ready=true;show();}else sessionChanged(data.session);});
  login.addEventListener('click',async()=>{
    const {data,error}=await client.auth.signInWithOAuth({provider:'github',options:{redirectTo:'https://andre8726.github.io/research-daily/',skipBrowserRedirect:true}});
    if(error){note.textContent='GitHub 登录尚未配置完成或暂时不可用';return;}
    location.assign(data.url);
  });
  logout.addEventListener('click',async()=>{if(busy||Object.keys(pending).length){note.textContent='请先同步待保存记录，再退出登录。';return;}const {error}=await client.auth.signOut();if(error)note.textContent='退出失败，请重试';});
  migrate.addEventListener('click',()=>{if(!user||!ready)return;const local=read('research-daily-reading-v1');for(const [key,value] of Object.entries(local)){if(!Object.hasOwn(reading,key)){reading[key]=value;pending[key]=value;}}cache();render();sync();});
  document.querySelector('#cloud-retry').addEventListener('click',sync);
  window.addEventListener('focus',sync);window.addEventListener('online',sync);
  setInterval(()=>{if(!document.hidden)sync();},60000);
})();
