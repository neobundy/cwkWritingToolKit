import sublime, sublime_plugin
import os, codecs

VERSION = "0.01"
WORDFILEPATH = os.path.join("Dictionaries", "dictionary.cwktxt")

class CwkInsertSelectedText(sublime_plugin.TextCommand):

	def run(self, edit, args):
		cursor = self.view.sel()[0]
		word_region = self.view.word(cursor)
		word = self.view.substr(word_region) 
		self.view.replace(edit, word_region, args['text'])
 
class CwkAutoComplete(sublime_plugin.WindowCommand):

	def __init__(self, window):

		self.plugin_settings = sublime.load_settings("cwkWritingToolKit.sublime-settings")
		super().__init__(window)
		self.debug = self.plugin_settings.get("debug", False)
		window = sublime.active_window()
		view = window.active_view()
		self.currentWord = view.substr(view.word(view.sel()[0].begin()))
		self._words = self.getWords(WORDFILEPATH)
		self._normalizedWords = []
		
	def run(self):

		window = sublime.active_window()
		view = window.active_view()
		self.log("view id: ", view.view_id)
		self.currentWord = view.substr(view.word(view.sel()[0].begin()))
		self.log("current word:", self.currentWord)
		self.normalizeWords()
		view.show_popup_menu(self._normalizedWords, self.on_done)

	def on_done(self, index):
		if index == -1: return
		selected_string = self._normalizedWords[index]
		self.log("Word selected: " , selected_string)
		window = sublime.active_window()
		view = window.active_view()

		view.run_command("cwk_insert_selected_text", {"args": {'text': selected_string.strip()} })

	def getWords(self, filename):
		word_lines = []
		if os.path.isfile(filename): 
			f = codecs.open(filename, "r", "utf-8")
			word_lines = f.readlines()
			self.log("cwk Dictionary Num Words Found: ", len(word_lines))
		else:
			self.log("cwk Dictionary file not found: ", filename)
		return word_lines

	def normalizeWords(self):
		self._normalizedWords = [ w.strip() for w in self._words if self.currentWord in w ]
		
	def log(self, *message):
		if(self.debug):
			print (*message)

