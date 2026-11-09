"""Compact, filterable model usage page with server-side pagination."""
import csv,io,time
from urllib.parse import urlencode
from datetime import datetime
import streamlit as st

STATUS={'running':'调用中','succeeded':'成功','failed':'失败','interrupted':'重启中断'}

def render(api,do,boot,roles):
    heading,refresh=st.columns([4,1],vertical_alignment='center')
    heading.title('调用日志')
    if refresh.button('刷新日志',use_container_width=True):st.rerun(scope='app')
    st.caption('记录角色模型调用及服务商返回的用量。素材搜索与本地合成不计作模型调用。')
    a,b,c,d=st.columns(4)
    role=a.selectbox('创作角色',['']+list(roles),format_func=lambda x:roles.get(x,'全部角色'))
    platform=b.selectbox('服务平台',['']+list(boot['catalog']),format_func=lambda x:boot['catalog'].get(x,{}).get('name','全部平台'))
    status=c.selectbox('调用结果',['']+list(STATUS),format_func=lambda x:STATUS.get(x,'全部结果'))
    days=d.selectbox('时间范围',[1,7,30,0],index=1,format_func=lambda x:f'近 {x} 天' if x else '全部时间')
    a,b=st.columns(2)
    project=a.selectbox('所属项目',['']+[p['id'] for p in boot['projects']],format_func=lambda x:next((p['name'] for p in boot['projects'] if p['id']==x),'全部项目（含连接测试）'))
    model=b.text_input('模型名称',placeholder='搜索模型 ID')
    query={'role':role,'platform':platform,'status':status,'project':project,'model':model,'days':days,'page':st.session_state.get('logs-page',1),'page_size':st.session_state.get('logs-size',12)}
    signature=(role,platform,status,project,model,days)
    if st.session_state.get('_logs_filter')!=signature:
        st.session_state['_logs_filter']=signature;st.session_state['logs-page']=1;query['page']=1
    result=do(lambda:api('/call-logs?'+urlencode(query)))
    if result is None:return
    st.session_state['logs-page']=result['page']
    totals=result['totals'];metrics=st.columns(5)
    metrics[0].metric('请求数',result['total']);metrics[1].metric('失败请求',result['failed'])
    metrics[2].metric('已报告 Token',f"{totals['total_tokens']:,.0f}" if 'total_tokens' in totals else '未提供')
    metrics[3].metric('已返回图片',str(totals['images']) if 'images' in totals else '未提供')
    metrics[4].metric('已报告视频秒数',f"{totals['video_seconds']:g} 秒" if 'video_seconds' in totals else '未提供')
    st.caption('汇总对应当前筛选范围。Token 不按字符估算；缓存 Token 属于输入明细，不重复相加。远程任务反复查询不重复累计用量。')
    rows=[]
    for item in result['items']:
        usage=item.get('usage',{})
        rows.append({'时间':datetime.fromtimestamp(item['created']).strftime('%m-%d %H:%M:%S'),'角色':roles.get(item['role'],item['role']),'平台':boot['catalog'].get(item['platform'],{}).get('name',item['platform']),'模型':item['model'],'操作':item['operation'],'结果':STATUS.get(item['status'],item['status']),'耗时（秒）':round(item.get('elapsed_ms',0)/1000,2),'输入 Token':usage.get('input_tokens'),'输出 Token':usage.get('output_tokens'),'总 Token':usage.get('total_tokens'),'图片':usage.get('images'),'视频秒数':usage.get('video_seconds')})
    if rows:st.dataframe(rows,hide_index=True,width='stretch')
    else:st.info('当前筛选下暂无调用记录。新增模型调用后会自动记录。')
    pages=max(1,(result['total']+result['page_size']-1)//result['page_size'])
    def move(delta):st.session_state['logs-page']=max(1,min(pages,st.session_state['logs-page']+delta))
    def reset():st.session_state['logs-page']=1
    with st.container(key='pagination-call-logs'):
        count,size,prev,page,next_col=st.columns([3,1.5,1,1.3,1],vertical_alignment='center')
        count.caption(f"共 {result['total']} 条 / {pages} 页")
        size.selectbox('每页数量',[12,24,48],key='logs-size',format_func=lambda x:f'{x} 条 / 页',label_visibility='collapsed',on_change=reset)
        prev.button('上一页',disabled=result['page']<=1,on_click=move,args=(-1,),use_container_width=True)
        page.number_input('页码',min_value=1,max_value=pages,key='logs-page',label_visibility='collapsed')
        next_col.button('下一页',disabled=result['page']>=pages,on_click=move,args=(1,),use_container_width=True)
    if rows:
        output=io.StringIO();writer=csv.DictWriter(output,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        st.download_button('导出本页 CSV',output.getvalue().encode('utf-8-sig'),file_name='model-calls.csv',mime='text/csv')
        with st.expander('查看调用详情',expanded=False):
            ids=[r['id'] for r in result['items']]
            chosen=st.selectbox('调用记录',ids,format_func=lambda x:next(r['model']+' / '+STATUS.get(r['status'],r['status'])+' / '+x[:8] for r in result['items'] if r['id']==x))
            record=next(r for r in result['items'] if r['id']==chosen)
            if record.get('error'):st.error(record['error'])
            if not record.get('usage'):st.caption('服务商未提供此请求的用量，未计入用量汇总。')
            st.json({k:record.get(k) for k in ('id','project','job','request_id','remote_id','http_status','parameters','usage')})
    st.caption('日志保存在本机，重启后保留；不记录 API Key、提示词正文、生成正文或图片数据。新增功能不追溯推算旧任务用量。')
