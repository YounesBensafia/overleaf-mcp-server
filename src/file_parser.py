from pylatexenc.latexwalker import LatexWalker, LatexEnvironmentNode, LatexMacroNode

def parse_latex(content):
    walker = LatexWalker(content)
    (nodes, pos, len_) = walker.get_latex_nodes()
    return nodes

def extract_equations(nodes):
    equations = []
    for node in nodes:
        if isinstance(node, LatexEnvironmentNode) and node.envname in ["equation", "align", "gather"]:
            equations.append(node)
        elif isinstance(node, LatexMacroNode) and node.macroname in ["begin"]:
            # Some manual checks for custom macros
            pass
    return equations

def extract_sections(nodes):
    sections = []
    for node in nodes:
        if isinstance(node, LatexMacroNode) and "section" in node.macroname:
            sections.append(node)
    return sections
