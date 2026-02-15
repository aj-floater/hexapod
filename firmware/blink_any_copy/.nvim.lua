local dap_file = vim.fn.getcwd() .. "/.nvim/dap-rp2040.lua"
if vim.fn.filereadable(dap_file) == 1 then
  dofile(dap_file)
end
