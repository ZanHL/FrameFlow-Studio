"""Separate one-frame image instructions from director/workflow and storyboard instructions."""
import re

SINGLE_FRAME_CONTRACT='''只生成一张完整、连续、铺满画幅的单场景图片。只画当前指定镜头的指定瞬间。
输出是可直接作为视频首帧或尾帧的画面，不是故事说明、分镜表、联系表、海报或设定页。
不分格、不拼贴、不分屏，不在同一图片中画多个镜头、多个时间状态或首尾帧对照。
画面没有镜头序号、说明文字、字幕、边框和水印。所有说明与元数据都只用于理解，不能画进图片。'''

_WORKFLOW=re.compile(r'审核|确认|预算|报价|费用|开工|充值|额度|尚未|待你|待审核|请确认|先制作|再制作|检查|片名|片长|成片|配乐|旁白|声音|故事[:：]|六镜|六段式|三视图|正面、侧面|样张供|粗剪')
_MULTI_FRAME=re.compile(r'(?:[AB甲乙]\s*首帧[：:].*?[AB甲乙]\s*首帧[：:]|[AB甲乙]\s*尾帧[：:].*?[AB甲乙]\s*尾帧[：:]|本镜分为.{0,30}(?:两个|2个).{0,8}(?:短镜|镜头))',re.S|re.I)

def visual_style(style):
    lines=[line.strip() for line in style.splitlines() if line.strip()]
    return '\n'.join(line for line in lines if not _WORKFLOW.search(line))

def validate_frame_description(text):
    if _MULTI_FRAME.search(text):
        raise ValueError('此帧规划包含 A/B 多个子镜或多个画面。请拆成独立镜头，或将首帧、尾帧各改成一个瞬间后再生成，未提交生图请求。')

def frame_prompt(project,shot,kind,text,instruction=''):
    validate_frame_description(text)
    label='首帧' if kind=='first' else '尾帧'
    return '\n\n'.join(part for part in [SINGLE_FRAME_CONTRACT,'当前任务元数据（不绘制）：'+str(shot.get('title',''))+' / '+label+' / '+project['ratio'],instruction,'视觉风格与外观基准：\n'+visual_style(project.get('style','')),'只画以下目标画面：\n'+text,'最终输出严格为一张单镜头'+label+'画面，不能出现其他镜头或分格版式。'] if part)

def style_sample_prompt(project,text):
    return SINGLE_FRAME_CONTRACT+'\n这是单张画风样张，不绘制正侧背多视图，不绘制故事分镜。\n视觉基准：\n'+visual_style(project.get('style',''))+'\n目标样张：\n'+text
