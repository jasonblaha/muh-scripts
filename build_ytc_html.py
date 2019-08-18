import json
import lxml.html
import lxml.etree
import os

CHANNEL_BASE = 'https://www.youtube.com/channel/'

PYTHON_FILE_PATH = os.path.dirname(os.path.realpath(__file__))
COMMENTS_FOLDER = PYTHON_FILE_PATH + '/html comment section'
if not os.path.exists(COMMENTS_FOLDER):
	os.makedirs(COMMENTS_FOLDER)
	
SCREENSHOT_ICON = '../screenshot.png'

def BuildHtmlFilepath(youtube_id):
	return os.path.join(COMMENTS_FOLDER, f'comments-{youtube_id}.html')

def CommentHTML(profile_icon, profile_name, profile_url, publish_date, comment_text, like_counter, screenshot_icon, profile_icon_size="43", profile_icon_offset="0", comment_width="600", screenshot_icon_size="43", font_size="16"):
	
	"""
		Returns HTML string part to append to the entire HTML string which
		resembles a part of the comment section.
	"""
	
	return f'<table><tr><td valign="top"><img src="{profile_icon}" style="margin-top: {font_size}px; margin-left: {profile_icon_offset}px;"></td><td style="width: {comment_width}px;"><p><a href={profile_url} target="_blank"><strong>{profile_name}</strong></a>&nbsp;{publish_date}<br>{comment_text}<br><br><em>Like counter: {like_counter}</em></p></td><td><img src="{screenshot_icon}" height="{screenshot_icon_size}" width="{screenshot_icon_size}" style="margin-left: {font_size}px;"></td></tr></table>'

def BuildCommentSectionHtml(metadata_filepath):
	
	"""
		Builds an HTML string and writes this to an .html file, indented.
	"""
	
	with open(metadata_filepath, 'r', encoding='utf-8') as f:
		comments_dict = json.loads(f.read())
	
	#extract id from comments metadata filepath
	basename, ext = os.path.splitext(metadata_filepath)
	youtube_id = basename[-11:]
	
	html_filepath = BuildHtmlFilepath(youtube_id)
	#create html document
	with open(html_filepath, 'w', encoding='utf-8') as f:
		
		#initialise html and create header
		html_str = f'<!DOCTYPE html><html><head><title>Comments on {youtube_id}</title></head>'
		
		#display comments amount
		html_str += '<h2>Comments: TEMPTY<\h2>'
		
		for comment_id in comments_dict:
			item = comments_dict[comment_id]
			
			user_url = CHANNEL_BASE + item['userid']
			username = item['username']
			user_icon = item['pic_url']
			post_text = item['post_text']
			post_time = item['post_time']
			like_counter = item['like_count']
			is_hearted = item['is_hearted'] #
			
			html_str += CommentHTML(user_icon, username, user_url, post_time, post_text, like_counter, SCREENSHOT_ICON)
			
			replies = item['replies']
			for reply_id in replies:
				reply_item = replies[reply_id]
				
				reply_user_url = CHANNEL_BASE + reply_item['userid']
				reply_username = reply_item['username']
				reply_user_icon = reply_item['pic_url']
				reply_post_text = reply_item['post_text']
				reply_post_time = reply_item['post_time']
				reply_like_counter = reply_item['like_count']
				reply_is_hearted = reply_item['is_hearted'] #
				
				html_str += CommentHTML(reply_user_icon, reply_username, reply_user_url, reply_post_time, reply_post_text, reply_like_counter, SCREENSHOT_ICON, profile_icon_offset="43")
				
		html_str += '</body></html>'
		
		#write *nice* html code to file. 
		document_root = lxml.html.fromstring(html_str).getroottree()
		f.write(lxml.etree.tostring(document_root, encoding='unicode', pretty_print=True))
		
	return html_filepath