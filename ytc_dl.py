import json
import lxml.html
import os
import re
import requests
import sys
import threading
import time
from tqdm import tqdm
import urllib.parse

from build_ytc_html import BuildCommentSectionHtml

session = requests.Session()
session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36'
session.headers['Accept-Language'] = 'en-GB,en;q=0.5'

lock = threading.Lock()

VIDEO_BASE_URL = 'https://www.youtube.com/watch?v='
INIT_COMMENTS_URL = 'https://www.youtube.com/watch_fragments2_ajax'
LOAD_COMMENTS_URL = 'https://www.youtube.com/comment_service_ajax'

COMMENT_PARAMS = {'action_get_comments': 1}
REPLY_PARAMS = {'action_get_comment_replies': 1}

PYTHON_FILE_PATH = os.path.dirname(os.path.realpath(__file__))
COMMENTS_FOLDER = PYTHON_FILE_PATH + '/downloaded comments'

if not os.path.exists(COMMENTS_FOLDER):
	os.makedirs(COMMENTS_FOLDER)

def find_value(html, key, num_chars):
	pos_begin = html.find(key) + len(key) + num_chars
	pos_end = html.find('"', pos_begin)
	return html[pos_begin:pos_end]

def unquoted_str(s):
	s_prev = s
	while True:
		s = urllib.parse.unquote(s)
		if s == s_prev:
			break
		else:
			s_prev = urllib.parse.unquote(s_prev)
	return s

def url_to_id(id_or_url):
	if len(id_or_url) == 11:
		vid_id = id_or_url
	else:
		try:
			vid_id = re.findall(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',id_or_url)[0]
		except IndexError:
			raise IndexError('Insert valid URL or ID string.')
	return vid_id


class ReplyThreadPool():

	"""
		Creates a limited number of threads and iterates
		through	commands stored in a list until it's done.
		Functions stored here get called from other classes
		generally.
		
		Initialised once in the program with:
		
		rtpool = ReplyThreadPool()
	"""
	
	queued_items = []
	
	current_threads = 0
	
	thread_history = []
	
	def __init__(self, max_threads=3):
		
		self._max_threads = max_threads
	
	def attempt_to_add_thread(self):
	
		"""
			(Attempt to) add a queued command to a thread, 
			when a new reply has been found or a thread is
			finished and there's an item in the queued_items 
			list.
			
			-"Remove" command from queued_items list
			-Call thread with command
			-increment current threads amount by one
		"""
		
		if self.current_threads < self._max_threads and self.queued_items:
			cmd = self.queued_items.pop(0)
			fr = FetchReplies(cmd)
			self.thread_history.append(fr)
			self.current_threads += 1
		
	def add_to_queue(self, cmd):
		
		"""
			Add command to queued_items list when
			a new reply has been found. Also attempt
			to add to thread afterwards.
			
			Notice no lock, this is called
		"""
		
		self.queued_items.append(cmd)
		self.attempt_to_add_thread()

	def task_done(self):
		
		"""
		Everytime a thread is done:
		-Decrement current threads amount by 1...
		-Attempt to add thread
		"""
		
		with lock:
			self.current_threads -= 1
			self.attempt_to_add_thread()

rtpool = ReplyThreadPool()

class FetchReplies(threading.Thread):
	
	"""
		NOTE:
		Everytime a thread is done:
		-Decrement current threads amount by 1...
		-"Remove" command from queued_items list
		-Add command to worker, increment current threads amount by one
	"""
	
	def __init__(self, cmd):
		threading.Thread.__init__(self)
		self.daemon = True
		self._cmd = cmd
		self.start()
	
	def run(self):
		
		global comments_dict
		
		#extract parameters from command
		session_token = self._cmd['session_token']
		comment_id = self._cmd['comment_id']
		first_reply_page_token = self._cmd['reply_page_token']
		
		reply_page_token = first_reply_page_token
		
		reply_data = {'session_token': session_token}
		while True:
			reply_data['page_token'] = reply_page_token
			#
			response = session.post(LOAD_COMMENTS_URL, params=REPLY_PARAMS, data=reply_data)
			response_dict = json.loads(response.text)
			#
			tree = lxml.html.fromstring(response_dict['content_html'])
			#
			reply_items = tree.cssselect('div.comment-renderer')
			#
			with lock:
				for reply_item in reply_items:
					#
					reply_id = reply_item.get('data-cid')
					#
					comments_dict[comment_id]['replies'][reply_id] = {
						'userid': reply_item.cssselect('.comment-author-text')[0].get('href').split('/')[2],
						'username': reply_item.cssselect('.comment-author-text')[0].text_content(),
						'pic_url':  reply_item.cssselect('.yt-thumb-clip img')[0].get('src'),
						'post_text': reply_item.cssselect('.comment-renderer-text-content')[0].text_content(),
						'post_time': reply_item.cssselect('.comment-renderer-time .yt-uix-sessionlink')[0].text_content(),
						'like_count': int(reply_item.cssselect('.comment-renderer-like-count')[-1].text_content())-1,
						'is_hearted': reply_item.cssselect('.creator-heart') != []
					}
				pbar.update(len(reply_items))
					
			#extract next page token to load more replies
			try:
				reply_page_token = unquoted_str(tree.cssselect('.yt-uix-button')[-1].get('data-uix-load-more-post-body').split('=')[1])	
			except AttributeError:
				break
		#
		rtpool.task_done()


class FetchComments():
	
	def __init__(self, id_or_url):
	
		global comments_dict, pbar
		
		comments_dict = {}
		
		youtube_id = url_to_id(id_or_url)
		session_token, comments_token = self.open_video_page(youtube_id)
		comment_amount, first_page_token = self.load_comments(youtube_id, session_token, comments_token)
		
		pbar = tqdm(total=comment_amount, desc='Fetching comments')
		self.fetch_comments(session_token, first_page_token)
		pbar.set_description('Fetching remainder')
		self.wait_until_threads_closed()
		pbar.set_description('Successful fetch')
		pbar.close()
		print('')
		
		json_filepath = self.write_json_file(youtube_id)
		print(f'Saved .json file as: "{json_filepath}"')
		
		html_filepath = BuildCommentSectionHtml(json_filepath)
		print(f'Saved .html file as: "{html_filepath}"')
		
		self.comments_dict = comments_dict.copy()
	
	def open_video_page(self, youtube_id):
	
		"""
			Actions on initial page load.
			
			Returns session token and comment token to 
			load comment amount and top comments.
		"""
		
		youtube_url = VIDEO_BASE_URL + youtube_id

		print('Opening video page URL: {youtube_url}'.format(youtube_url=youtube_url))

		#load the video page, extract tokens
		response = session.get(youtube_url)
		html = response.text

		session_token = find_value(html, 'XSRF_TOKEN', 4)
		comments_token = find_value(html, 'COMMENTS_TOKEN', 4)
		
		return session_token, comments_token
	
	def load_comments(self, youtube_id, session_token, comments_token):
	
		"""
			Create request to fetch (top-rated) comments, comment 
			amount and page-token to fetch newest comments.
			
			Returns comments amount and page token to load "newest
			first" comments. 
		"""
		
		print('Loading comment section...')

		#headers for ajax request; firefox: inspect element, networks
		init_comment_params = {'v': youtube_id, 
			'tr': 'scroll', 
			'distiller': 1, 
			'ctoken': comments_token, 
			'frags': 'comments', 
			'spf': 'load'
		}
		
		init_data = {'session_token': session_token,
			'client_url': VIDEO_BASE_URL + youtube_id
		}
		
		#make request
		response = session.post(INIT_COMMENTS_URL, params=init_comment_params, data=init_data)

		#parse request to dict and tree
		response_dict = json.loads(response.text)
		tree = lxml.html.fromstring(response_dict['body']['watch-discussion'])

		#css selector for comment amount and get comment amount
		comment_amount_str = tree.cssselect('.comment-section-header-renderer')[0].text_content().strip(' \n')
		for c in comment_amount_str.split(' '):
			try:
				comment_amount = int(c)
			except ValueError:
				pass
		
		# # #
		# # # First comments too?
		# # #
		
		print(f'Total: {comment_amount} comments...')

		#extract "newest first" token
		first_page_token = unquoted_str(tree.cssselect('.yt-ui-menu-item')[1].get('data-token'))
		
		return comment_amount, first_page_token
	
	def fetch_comments(self, session_token, first_page_token):
		
		"""
			Make request to get newest comments, slightly different
			than the request in load_comments.
		""" 	
		
		global comments_dict
		
		page_token = first_page_token
		
		comment_data = {'session_token': session_token}
		while True:
			comment_data['page_token'] = page_token
			#make request
			response = session.post(LOAD_COMMENTS_URL, params=COMMENT_PARAMS, data=comment_data)
			response_dict = json.loads(response.text)
			# extract comments
			tree = lxml.html.fromstring(response_dict['content_html'])
			#get comments
			items = tree.cssselect('section.comment-thread-renderer')
			#
			with lock:
				for item in items:
					#extract user id
					comment_id = item.cssselect('div.comment-renderer')[0].get('data-cid')
					#extract comment data and put in the dict
					comments_dict[comment_id] = {
						'userid': item.cssselect('.comment-author-text')[0].get('href').split('/')[2],
						'username': item.cssselect('.comment-author-text')[0].text_content(),
						'pic_url':  item.cssselect('.yt-thumb-clip img')[0].get('src'),
						'post_text': item.cssselect('.comment-renderer-text-content')[0].text_content(),
						'post_time': item.cssselect('.comment-renderer-time .yt-uix-sessionlink')[0].text_content(),
						'like_count': int(item.cssselect('.comment-renderer-like-count')[-1].text_content())-1,
						'is_hearted': item.cssselect('.creator-heart') != [],
						'replies': {}
					}
					#extract reply page token
					reply_item = item.cssselect('.comment-replies-renderer .yt-uix-button')
					if reply_item != []:
						reply_page_token = unquoted_str(reply_item[0].get('data-uix-load-more-post-body').split('=')[1])
						#fetch replies in separate thread
						cmd = {
							'session_token': session_token,
							'comment_id': comment_id, 
							'reply_page_token': reply_page_token
						}
						rtpool.add_to_queue(cmd)
				pbar.update(len(items))
						
			#extract next page token to load more top level comments
			try:
				tree = lxml.html.fromstring(response_dict['load_more_widget_html'])
			except KeyError:
				break
				
			page_token = unquoted_str(tree.cssselect('.yt-uix-button')[0].get('data-uix-load-more-post-body').split('=')[1])
	
	def wait_until_threads_closed(self):
		
		"""
			Wait until all reply threads are done and 
			there are no queued_items.
		"""
		
		while True:
		
			no_threads_alive = True
			
			for f in rtpool.thread_history:
				if f.is_alive():
					no_threads_alive = False
			
			if no_threads_alive and not rtpool.queued_items:
				break
			else:
				time.sleep(0.2)
	
	def write_json_file(self, youtube_id):
		
		filename = f'comments-{youtube_id}.json'
		filepath = os.path.join(COMMENTS_FOLDER, filename)
		
		with open(filepath, 'w', encoding='utf-8') as f:
			json.dump(comments_dict, f, indent=4)
		
		return filepath

if __name__ == '__main__':
	
	cmd_args = sys.argv[1]
	
	fc_lst = []
	
	for youtube_url in cmd_args.split(','):
		fc = FetchComments(youtube_url)
		fc_lst.append(fc)
		
	
	