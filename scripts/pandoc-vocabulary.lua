-- Emit Pandoc's own AST vocabulary, one `kind<TAB>name` line per exposed name.
--
-- `constructor` names are the functions that build AST nodes. `tag` names are the string
-- constants Pandoc uses for a node's sub-type — alignments, quote kinds, list styles — which
-- appear as `{"t": name}` in native JSON but are never blocks or inlines themselves.
function Pandoc(_document)
  local names = {}
  for name, value in pairs(pandoc) do
    if string.match(name, "^[A-Z]") then
      if type(value) == "function" then
        table.insert(names, "constructor\t" .. name)
      elseif type(value) == "string" then
        table.insert(names, "tag\t" .. name)
      end
    end
  end
  table.sort(names)
  io.write(table.concat(names, "\n"))
  io.write("\n")
  return pandoc.Pandoc({})
end
