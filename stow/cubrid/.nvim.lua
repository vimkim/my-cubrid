vim.api.nvim_create_autocmd({ "FileType" }, {
	pattern = { "c", "cpp", "h", "hpp", "cmake", "sh" },
	callback = function()
		vim.b.autoformat = false
	end,
})

-- Set tab settings specifically for C and C++ files
vim.api.nvim_create_autocmd("FileType", {
	pattern = { "c", "cpp", "h", "hpp", "cc", "hh" },
	callback = function()
		vim.bo.cindent = true
		vim.bo.indentexpr = ""
		vim.bo.cinoptions = "j1,f0,^-2,{2,>4,:4,n-2,(0,t0"
		vim.bo.shiftwidth = 2
		vim.bo.tabstop = 8
		vim.bo.expandtab = false
	end,
})

vim.filetype.add({
	extension = { i = "c" },
})
