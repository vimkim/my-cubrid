local grp = vim.api.nvim_create_augroup("ProjectCStyle", { clear = true })

vim.api.nvim_create_autocmd({ "FileType" }, {
	group = grp,
	pattern = { "c", "cpp", "cmake", "sh" },
	callback = function()
		vim.b.autoformat = false
	end,
})

-- Set tab settings specifically for C and C++ files
vim.api.nvim_create_autocmd("FileType", {
	group = grp,
	pattern = { "c", "cpp", "yacc", "lex" },
	callback = function()
		vim.bo.cindent = true
		vim.bo.indentexpr = ""
		vim.bo.cinoptions = "j1,f0,^-2,{2,>4,:4,n-2,(0,t0"
		vim.bo.shiftwidth = 2
		vim.bo.tabstop = 8
		vim.bo.expandtab = false
	end,
})

-- Optional: shell files separate (C-style cindent is wrong for sh)
vim.api.nvim_create_autocmd("FileType", {
	group = grp,
	pattern = { "sh" },
	callback = function()
		-- no cindent for shell files
		vim.bo.expandtab = true
		vim.bo.shiftwidth = 2
		vim.bo.softtabstop = 2
		vim.bo.tabstop = 2
	end,
})

vim.filetype.add({
	extension = { i = "c" },
})
