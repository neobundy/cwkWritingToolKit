import sublime, sublime_plugin
import os, codecs, urllib, re
from html.parser import HTMLParser

VERSION = "0.02"

# English Dictionary: Naver
WEB_ENGLISH_DIC_URL = "http://endic.naver.com/search.nhn?%s"
WEB_ENGLISH_DIC_OPTIONS = "query={query}&searchOption=thesaurus"

# Korean Dictionary: Naver
WEB_KOREAN_DIC_URL = "http://krdic.naver.com/search.nhn?kind=keyword&%s"
WEB_KOREAN_DIC_OPTIONS = "query={query}"

# Japanese Dictionary: Naver
WEB_JAPANESE_DIC_URL = "http://jpdic.naver.com/search.nhn?%s"
WEB_JAPANESE_DIC_OPTIONS = "q={query}"


ENGLISH_TARGET_BLOCK_TAG = 'span'
ENGLISH_TARGET_SYNONYM_TAG = 'a'
ENGLISH_TARGET_SYNONYM_LABEL = '[유의어]' 

KOREAN_TARGET_SYNONYM_TAG = 'a' 
KOREAN_TARGET_SYNONYM_CLASS_ID = 'syno'

JAPANESE_TARGET_BLOCK_TAG = 'span'
JAPANESE_TARGET_KEYWORD = '[유의어]' 
JAPANESE_TARGET_SYNONYM_TAG = 'a'

# Python idiom: os-independent file path 

package_path = os.path.join(sublime.packages_path(), "cwkWritingToolKit")
WORD_FILE_PATH = os.path.join("Dictionaries", "dictionary.cwktxt")
WORD_FILE_PATH  = os.path.join(package_path, WORD_FILE_PATH)

class cwkUtil:
	def __init__(self):
		self.plugin_settings = sublime.load_settings("cwkWritingToolKit.sublime-settings")
		self.debug = self.plugin_settings.get("debug", False)
		self._words = []

	def log(self, *message):
	# utility method to print out debug messages

		# note that print is not a statement anymore in Python 3. It's a function.
		# print "blah blah" will give you an error
		# use print("blah blah") instead

		if(self.debug):
			print (*message)
	def isKorean(self, word):
		if re.match(r'(^[가-힣]+)', word): 
			return True
		else: 
			return False
	def isEnglish(self, word):
		if re.match(r'(^[a-bA-B]+)', word): 
			return True
		else: 
			return False
	def removeTags(self, line):
		pattern = re.compile(r'<[^>]+>')
		return pattern.sub('', line)

class cwkWebDicParser(HTMLParser, cwkUtil):
	def __init__(self):
		HTMLParser.__init__(self)
		cwkUtil.__init__(self)

	def getWords(self):
		return self._words


class cwkEnglishWebDicParser(cwkWebDicParser):
	def __init__(self):
		cwkWebDicParser.__init__(self)
		self._is_in_block = False
		self._ENGLISH_TARGET_BLOCK_TAG_found = False
		self._ENGLISH_TARGET_SYNONYM_TAG_found = False
		self._target_defs_tag_found = False
		self._is_final_tag = False
		self.synonym = ''


	def handle_starttag(self, tag, attrs):
		if tag == ENGLISH_TARGET_BLOCK_TAG:
			# target tag found

			if self._is_in_block and self._is_final_tag:
				self.reset_tags()
				self._target_defs_tag_found = True
			else:
				self._ENGLISH_TARGET_BLOCK_TAG_found = True

		elif tag == ENGLISH_TARGET_SYNONYM_TAG and self._is_in_block:
			# synonym tag found

			self._ENGLISH_TARGET_SYNONYM_TAG_found = True
		else:
			# false alarm

			self.reset_tags()

	def handle_endtag(self, tag):
		pass
		
	def handle_data(self, data):
		if not self._is_in_block and self._ENGLISH_TARGET_BLOCK_TAG_found and data.strip() == ENGLISH_TARGET_SYNONYM_LABEL:
			#keyword found: block starts.

			self._is_in_block = True
			self.log("Keyword:", data)
		elif self._is_in_block and self._ENGLISH_TARGET_SYNONYM_TAG_found:
			#synonym tag found: gather synonym

			self.synonym = data
			self._ENGLISH_TARGET_SYNONYM_TAG_found = False
			self._is_final_tag = True
		elif self._target_defs_tag_found:
			# synonym definitions found: gather defs

			self.log("Synonym:" , self.synonym)
			self.log("Defs:", data)
			defs = data.split(",")
			self._words.append(self.synonym)
			self.log("Appending synonym: ", self.synonym)
			for d in defs:
				self._words.append("\t {0}".format(d))
				self.log("Appending def: ",  d)
			self.synonym = ''
			self.reset_tags()
		else:
			# reset and get ready to go again

			self.reset_tags()


	def reset_tags(self):
		self._is_in_block = False
		self._ENGLISH_TARGET_BLOCK_TAG_found = False
		self._ENGLISH_TARGET_SYNONYM_TAG_found = False
		self._target_defs_tag_found = False
		self._is_final_tag = False

class cwkKoreanWebDicParser(cwkWebDicParser):
	def __init__(self):
		cwkWebDicParser.__init__(self)
		self._target_synonym_found = False

	def handle_starttag(self, tag, attrs):
		if tag == KOREAN_TARGET_SYNONYM_TAG:
			for name, value in attrs:
				if name == 'class' and value == KOREAN_TARGET_SYNONYM_CLASS_ID:
					self._target_synonym_found = True
		else:
			# false alarm
			self.reset_tags()

	def handle_endtag(self, tag):
		pass
		
	def handle_data(self, data):
		
		data = self.removeTags(data)
		if self._target_synonym_found:
			self.log("synonym:", data)
			if self.isKorean(data):
				self._words.append(data)


	def reset_tags(self):
		self._target_synonym_found = False

# cwk_fetch_WEB_ENGLISH_DIC text command inserts one of the synonym definitions fetched from the given web dictionary.
# camel casing: CwkFetchWebDic
# snake casing: cwk_fetch_WEB_ENGLISH_DIC 
# Sublime Text translates camel cased commands into snake cased ones.
# You can run snake cased command by calling the view's run_command() method as the following:
# 	view.run_command("cwk_fetch_WEB_ENGLISH_DIC", text_to_insert)

class CwkFetchWebDic(sublime_plugin.TextCommand, cwkUtil):
	def __init__(self, *args, **kwargs):
		sublime_plugin.TextCommand.__init__(self, *args, **kwargs)
		cwkUtil.__init__(self)
	def run(self, edit):

		# get active window and view

		window = sublime.active_window()
		view = window.active_view()

		# save the word at the cursor position

		self.currentWord = view.substr(view.word(view.sel()[0].begin()))

		if self.currentWord:
			self.log("Word selected: ", self.currentWord)

			if self.isEnglish(self.currentWord):
				options = WEB_ENGLISH_DIC_OPTIONS.format(query=self.currentWord)
				request = urllib.request.Request(WEB_ENGLISH_DIC_URL % options)

				self.log("Web Dic URL: " , WEB_ENGLISH_DIC_URL % options)

				response = urllib.request.urlopen(request)
				webpage = response.read().decode('utf-8')

				parser = cwkEnglishWebDicParser()

			elif self.isKorean(self.currentWord):
				encoded_query = urllib.parse.quote(self.currentWord)
				self.log("Encoded Korean: ", encoded_query)
				options = WEB_KOREAN_DIC_OPTIONS.format(query=encoded_query)
				request = urllib.request.Request(WEB_KOREAN_DIC_URL % options)

				self.log("Web Dic URL: " , WEB_KOREAN_DIC_URL % options)

				response = urllib.request.urlopen(request)
				webpage = response.read().decode('utf-8')

				parser = cwkKoreanWebDicParser()


			parser.feed(webpage)

			self._words = parser.getWords()

			self.log("Num synonyms found: ", len(self._words))
			view.show_popup_menu(self._words, self.on_done)

	def on_done(self, index):
	#show_popup_menu callback method 
	
		# if the use canceled out of the popout menu, -1 is returned. Otherwise the index is returned.

		if index == -1: return

		selected_string = self._words[index]
		window = sublime.active_window()
		view = window.active_view()

		# run Text Command cwk_insert_selected_text to replace the current word with the user's choice

		view.run_command("cwk_insert_selected_text", {"args": {'text': selected_string.strip()} })

# cwk_insert_selected_text command inserts text at cursor position
# camel casing: CwkInsertSelectedText
# snake casing: cwk_insert_selected_text
# Sublime Text translates camel cased commands into snake cased ones.
# You can run snake cased command by calling the view's run_command() method as the following:
# 	view.run_command("cwk_insert_selected_text", text_to_insert)

class CwkInsertSelectedText(sublime_plugin.TextCommand, cwkUtil):
	def run(self, edit, args):
		
		# get current cursor position
		# Sublime Text supports multiple cursors: view.sel() returns the list of those cursors. The first element of the list refers to the current cursor position.
		# view.word() returns the region of the current word.

		cursor = self.view.sel()[0]
		word_region = self.view.word(cursor)
		word = self.view.substr(word_region) 

		# view.replace() replaces the selected word with the given text. edit is the buffer currently in use.

		self.view.replace(edit, word_region, args['text'])
 
class CwkAutoComplete(sublime_plugin.WindowCommand, cwkUtil):
	def __init__(self, window):

		# super() refers to the immediate ancestor: sublime_plugin.WindowCommand in this case.

		super().__init__(window)
		cwkUtil.__init__(self)

		# get active window and view

		window = sublime.active_window()
		view = window.active_view()

		# save the word at the cursor position

		self.currentWord = view.substr(view.word(view.sel()[0].begin()))

		# self._words stores all found words whereas self._normalizedWords stores unique values.

		self._words = self.getWords(WORD_FILE_PATH)
		self._normalizedWords = []
		
	def run(self): 
	# run method is triggered when this cwk_auto_comoplete command is called

		window = sublime.active_window()
		view = window.active_view()

		# self.log() spits out messages only when debug mode is on, that is, set to true.

		self.log("view id: ", view.view_id)
		self.currentWord = view.substr(view.word(view.sel()[0].begin()))
		self.log("current word:", self.currentWord)
		self.normalizeWords()

		# view.shop_popup_menu() displays a popout menu presenting the words that contain the self.currentWord.
		# self.on_done is a callback method to be called when a selection is made.

		view.show_popup_menu(self._normalizedWords, self.on_done)

	def on_done(self, index):
	#show_popup_menu callback method 
	
		# if the use canceled out of the popout menu, -1 is returned. Otherwise the index is returned.

		if index == -1: return

		selected_string = self._normalizedWords[index]
		self.log("Word selected: " , selected_string)
		window = sublime.active_window()
		view = window.active_view()

		# run Text Command cwk_insert_selected_text to replace the current word with the user's choice

		view.run_command("cwk_insert_selected_text", {"args": {'text': selected_string.strip()} })

	def getWords(self, filename):
	# creates a autocomplete dictionary from the dictionary file

		word_lines = []
		if os.path.isfile(filename): 

			# normal file operations won't work with Korean characters. use codecs library instead.  
			# open() method returns a file handle and readlines() method returns the file contents as a list of lines.

			f = codecs.open(filename, "r", "utf-8")
			word_lines = f.readlines()
			self.log("cwk Dictionary Num Words Found: ", len(word_lines))
		else:
			self.log("cwk Dictionary file not found: ", filename)
		return word_lines

	def normalizeWords(self):
	# selects only those words that match the current word

		# Python idiom: list comprehension
		# discards the words not matching the current word and strip whitespaces at both ends

		self._normalizedWords = [ w.strip() for w in self._words if self.currentWord in w ]
		

