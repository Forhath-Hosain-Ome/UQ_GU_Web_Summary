import { useState } from "react";
import { SectionGroup } from "../SectionGroup"
import { MENU_GROUPS } from "../../shared/apiGroup"

const METHOD_COLORS = {
  GET:  { bg: "rgba(34,211,160,0.1)",  text: "var(--color-success)" },
  POST: { bg: "rgba(99,102,241,0.12)", text: "var(--color-accent2)" },
};

export default function ApiMenu({ onSelect, activeId, groups = MENU_GROUPS }) {
  const [collapsed, setCollapsed] = useState({});

  return (
    <nav className="api_menu">
      <div className="label">
        <span className="text-[10px] font-medium tracking-wildest text-muted" >
          API
        </span>
        <div className="text-[9px] accent-accent mt-0.75" >
          /Path/
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2" >
        {groups.map((group) => (
          <div key={group.title}>
            <div className="text-[10px] text-muted mb-2 tracking-widest">
              {groups.title}
            </div>
            {group.sections.map((section) => 
                <SectionGroup key={section.label} section={section} collapsed={collapsed} setCollapsed={setCollapsed} activeId={activeId}  onSelect={onSelect} METHOD_COLORS={METHOD_COLORS} />
              )
            }

          </div>
        ))}
      </div>
    </nav>
  );
}