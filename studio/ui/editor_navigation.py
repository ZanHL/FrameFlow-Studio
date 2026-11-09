"""Shared project-editor breadcrumb, back action and in-page section navigation."""
from html import escape
import streamlit as st

def render(project_id,project_name,mode,sections=()):
    st.markdown('''<style>
.editor-breadcrumbs{display:flex;align-items:center;flex-wrap:nowrap;gap:10px;height:36px;font-size:13px;line-height:36px;color:#7b8498;overflow:hidden}
.editor-breadcrumbs>*{margin:0!important;padding:0;line-height:36px!important;font-size:inherit!important}
.editor-breadcrumbs a{color:#768096;text-decoration:none;flex-shrink:0;white-space:nowrap}
.editor-breadcrumbs a:hover{color:#6953c6;text-decoration:underline;text-underline-offset:4px}
.editor-breadcrumbs a:focus-visible{outline:2px solid #bcb0ee;outline-offset:2px}
.editor-breadcrumbs .mode{flex-shrink:0;white-space:nowrap}
.editor-breadcrumbs .current-project{color:#30384e;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.editor-breadcrumbs .separator{color:#bac1cf;flex-shrink:0}
.editor-section-nav{display:flex;flex-wrap:wrap;gap:8px;padding:12px 0 16px;border-bottom:1px solid #e2e6ef;margin-bottom:8px}
.editor-section-nav a{font-size:13px;line-height:32px;padding:0 16px;border:1px solid #e2e6ef;border-radius:6px;color:#576077;text-decoration:none;background:#fff}
.editor-section-nav a:hover{border-color:#b7aaeb;color:#6953c6;background:#f4f1ff}
.editor-section-nav a:focus-visible{outline:3px solid #bcb0ee;outline-offset:2px}
h2[id],h3[id]{scroll-margin-top:80px}
@media(max-width:760px){.editor-breadcrumbs{font-size:12px}.editor-section-nav a{padding:0 12px}}
</style>''',unsafe_allow_html=True)
    with st.container(key='editor-navigation-'+project_id):
        st.markdown('<nav aria-label="项目路径" class="editor-breadcrumbs"><a href="?page=overview" target="_self">项目总览</a><span class="separator">/</span><span class="mode">'+escape(mode)+'</span><span class="separator">/</span><span class="current-project" aria-current="page" title="'+escape(project_name,quote=True)+'">'+escape(project_name)+'</span></nav>',unsafe_allow_html=True)
        if sections:
            links=''.join('<a href="#'+escape(anchor,quote=True)+'">'+escape(label)+'</a>' for label,anchor in sections)
            st.markdown('<nav class="editor-section-nav" aria-label="快速制作环节">'+links+'</nav>',unsafe_allow_html=True)
