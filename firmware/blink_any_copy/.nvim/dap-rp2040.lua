local ok, dap = pcall(require, "dap")
if not ok then
  vim.notify("nvim-dap is not installed", vim.log.levels.ERROR)
  return
end

local home = os.getenv("HOME") or ""
local default_gdb = home .. "/.pico-sdk/toolchain/13_2_Rel1/bin/arm-none-eabi-gdb"
local gdb = os.getenv("GDB_BIN") or default_gdb

dap.adapters.gdb = {
  type = "executable",
  command = gdb,
  args = { "-i", "dap" },
}
dap.adapters["cortex-debug"] = dap.adapters.gdb

dap.configurations.c = {
  {
    name = "RP2040: Attach OpenOCD (:3333)",
    type = "gdb",
    request = "launch",
    cwd = "${workspaceFolder}",
    program = "${workspaceFolder}/build-blink_any_copy/blink_any.elf",
    target = "localhost:3333",
    stopAtBeginningOfMainSubprogram = true,
  },
}

dap.configurations.cpp = dap.configurations.c

vim.keymap.set("n", "<F5>", function()
  dap.continue()
end, { desc = "DAP Continue" })

vim.keymap.set("n", "<F10>", function()
  dap.step_over()
end, { desc = "DAP Step Over" })

vim.keymap.set("n", "<F11>", function()
  dap.step_into()
end, { desc = "DAP Step Into" })

vim.keymap.set("n", "<F12>", function()
  dap.step_out()
end, { desc = "DAP Step Out" })

vim.keymap.set("n", "<Leader>db", function()
  dap.toggle_breakpoint()
end, { desc = "DAP Toggle Breakpoint" })

vim.keymap.set("n", "<Leader>dr", function()
  dap.repl.open()
end, { desc = "DAP Open REPL" })

vim.keymap.set("n", "<Leader>dt", function()
  dap.terminate()
end, { desc = "DAP Terminate" })

local function pico_term_tab(command)
  vim.cmd("tabnew")
  vim.fn.termopen("cd /home/arjames/Coding/hexapod/firmware/blink_any_copy && " .. command)
  vim.opt_local.number = false
  vim.opt_local.relativenumber = false
  vim.cmd("startinsert")
end

vim.keymap.set("n", "<Leader>pb", function()
  pico_term_tab("make build")
end, { desc = "[P]ico [B]uild" })

vim.keymap.set("n", "<Leader>pd", function()
  pico_term_tab("make debug")
end, { desc = "[P]ico [D]ebug" })

vim.keymap.set("n", "<Leader>pf", function()
  pico_term_tab("make flash")
end, { desc = "[P]ico [F]lash" })
