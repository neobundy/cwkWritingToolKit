import sublime, sublime_plugin
import os, codecs

VERSION = "0.01"
WORDFILEPATH = os.path.join("Dictionaries", "dictionary.cwktxt")

class CwkInsertSelectedText(sublime_plugin.TextCommand):

	def run(self, edit, args):
		self.view.insert(edit, self.view.sel()[0].begin(), args['text'])

class CwkAutoComplete(sublime_plugin.WindowCommand):

	def __init__(self, window):

		self.plugin_settings = sublime.load_settings("cwkWritingToolKit.sublime-settings")
		super().__init__(window)
		self.debug = self.plugin_settings.get("debug", False)
		self._words = self.getWords(WORDFILEPATH)

	def run(self):

		window = sublime.active_window()
		view = window.active_view()
		self.log("view id: ", view.view_id)

		view.show_popup_menu(self._words, self.on_done)

	def on_done(self, index):
		if index == -1: return
		selected_string = self._words[index]
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

	def log(self, *message):
		if(self.debug):
			print (*message)

