import type { ReactNode } from 'react';
import {
  BellRing,
  CalendarDays,
  Check,
  FileText,
  Heart,
  Lightbulb,
  LockKeyhole,
  Mail,
  Mic,
  MousePointer2,
  Phone,
  Play,
  Radio,
  Search,
  ShieldCheck,
  Sparkles,
  Sun,
  UserRound,
} from 'lucide-react';
import { FEATURE_SCENES, type FeatureScene } from './FeatureScenes';

function Lines({
  x,
  y,
  width = 80,
  rows = 3,
}: {
  x: number;
  y: number;
  width?: number;
  rows?: number;
}) {
  return Array.from({ length: rows }, (_, i) => (
    <rect
      key={i}
      x={x}
      y={y + i * 10}
      width={width * (i === rows - 1 ? 0.65 : 1)}
      height="3"
      rx="1.5"
      fill="currentColor"
      opacity="0.2"
    />
  ));
}

function Sheet({
  x,
  y,
  width,
  height,
  children,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  children?: ReactNode;
}) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx="8"
        className="fill-card"
        stroke="currentColor"
        strokeOpacity="0.22"
      />
      {children}
    </g>
  );
}

function Wave({ x, y, width = 100 }: { x: number; y: number; width?: number }) {
  const heights = [6, 12, 22, 13, 32, 22, 38, 16, 28, 12, 20, 7];
  return heights.map((height, i) => (
    <rect
      key={i}
      x={x + (i * width) / heights.length}
      y={y - height / 2}
      width="3.5"
      height={height}
      rx="1.75"
      fill="currentColor"
      opacity={0.35 + (i % 3) * 0.2}
    />
  ));
}

function Plan() {
  return (
    <>
      <Sheet x={25} y={16} width={270} height={36}>
        <Sparkles x="38" y="26" width="16" height="16" />
        <Lines x={65} y={27} width={192} rows={2} />
      </Sheet>
      <path
        d="M160 52v14M75 77V66h170v11M160 66v11"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.3"
      />
      {[CalendarDays, Mail, FileText].map((Icon, i) => (
        <g key={i}>
          <Sheet x={30 + i * 88} y={78} width={80} height={62}>
            <Icon x={43 + i * 88} y="88" width="17" height="17" />
            <Lines x={43 + i * 88} y={116} width={48} rows={2} />
            <Check x={87 + i * 88} y="91" width="12" height="12" />
          </Sheet>
        </g>
      ))}
    </>
  );
}

function Call() {
  return (
    <>
      <Sheet x={34} y={13} width={89} height={133}>
        <circle cx="78" cy="56" r="20" fill="currentColor" opacity="0.09" />
        <Phone x="68" y="46" width="20" height="20" />
        <Wave x={51} y={100} width={59} />
        <rect x="65" y="129" width="26" height="3" rx="1.5" fill="currentColor" opacity="0.2" />
      </Sheet>
      <path d="M132 78h25l-5-5m5 5-5 5" stroke="currentColor" strokeOpacity="0.4" fill="none" />
      <Sheet x={166} y={31} width={117} height={103}>
        <FileText x="180" y="45" width="19" height="19" />
        <Lines x={180} y={76} width={87} rows={3} />
        <Check x="180" y="112" width="12" height="12" />
        <Lines x={199} y={116} width={63} rows={1} />
      </Sheet>
    </>
  );
}

function Voice() {
  return (
    <>
      <Sheet x={30} y={23} width={197} height={51}>
        <Mic x="44" y="39" width="20" height="20" />
        <Wave x={78} y={49} width={130} />
      </Sheet>
      <Sheet x={93} y={89} width={197} height={51}>
        <Sparkles x="108" y="105" width="20" height="20" />
        <Wave x={143} y={114} width={130} />
      </Sheet>
      <path
        d="M43 74v10l15-10M276 140v9l-15-9"
        stroke="currentColor"
        strokeOpacity="0.22"
        fill="none"
      />
    </>
  );
}

function Document() {
  return (
    <>
      <g transform="rotate(-7 112 84)">
        <Sheet x={66} y={24} width={110} height={119}>
          <Lines x={82} y={47} width={76} rows={7} />
        </Sheet>
      </g>
      <Sheet x={119} y={10} width={131} height={139}>
        <FileText x="135" y="25" width="18" height="18" />
        <rect x="164" y="29" width="64" height="6" rx="3" fill="currentColor" opacity="0.6" />
        <Lines x={135} y={56} width={95} rows={3} />
        {[28, 44, 34, 51].map((height, i) => (
          <rect
            key={i}
            x={138 + i * 22}
            y={136 - height}
            width="13"
            height={height}
            rx="3"
            fill="currentColor"
            opacity={0.2 + i * 0.12}
          />
        ))}
      </Sheet>
    </>
  );
}

function Browser() {
  return (
    <>
      <Sheet x={29} y={15} width={262} height={130}>
        <path d="M29 38h262" stroke="currentColor" strokeOpacity="0.2" />
        {[43, 53, 63].map(x => (
          <circle key={x} cx={x} cy="27" r="2" fill="currentColor" opacity="0.4" />
        ))}
        <rect x="96" y="23" width="132" height="8" rx="4" fill="currentColor" opacity="0.08" />
        <rect x="44" y="51" width="66" height="77" rx="4" fill="currentColor" opacity="0.1" />
        <Lines x={123} y={54} width={142} rows={3} />
        <rect x="123" y="94" width="98" height="24" rx="5" fill="currentColor" opacity="0.15" />
        <Check x="134" y="99" width="14" height="14" />
        <MousePointer2 x="211" y="106" width="28" height="28" className="fill-card" />
      </Sheet>
    </>
  );
}

function Calculation() {
  return (
    <>
      <Sheet x={35} y={22} width={160} height={116}>
        <rect x="47" y="35" width="137" height="15" rx="3" fill="currentColor" opacity="0.15" />
        {[61, 83, 105].map(y => (
          <g key={y}>
            <path d={`M47 ${y + 13}h137`} stroke="currentColor" strokeOpacity="0.1" />
            <Lines x={50} y={y} width={34} rows={1} />
            <Lines x={114} y={y} width={23} rows={1} />
            <Lines x={153} y={y} width={26} rows={1} />
          </g>
        ))}
      </Sheet>
      <Sheet x={207} y={40} width={78} height={80}>
        <path
          d="M220 103h51M223 100V86h9v14m9 0V72h9v28m9 0V57h9v43"
          fill="currentColor"
          fillOpacity="0.2"
          stroke="currentColor"
          strokeOpacity="0.4"
        />
      </Sheet>
    </>
  );
}

function ImageArt() {
  return (
    <>
      <Sheet x={46} y={19} width={231} height={125}>
        <rect x="57" y="30" width="209" height="91" rx="5" fill="currentColor" opacity="0.06" />
        <circle cx="225" cy="51" r="12" fill="currentColor" opacity="0.35" />
        <path d="M57 120 123 47l56 73Z" fill="currentColor" opacity="0.22" />
        <path d="m142 120 66-60 58 60Z" fill="currentColor" opacity="0.4" />
        <Lines x={59} y={131} width={126} rows={1} />
      </Sheet>
      <Sparkles x="24" y="96" width="25" height="25" />
    </>
  );
}

function Diagram() {
  return (
    <>
      <path
        d="M160 49v24M76 89V73h168v16M76 113v24h168v-24"
        stroke="currentColor"
        strokeOpacity="0.35"
        fill="none"
        strokeDasharray="4 4"
      />
      <Sheet x={112} y={14} width={96} height={35}>
        <Lines x={130} y={29} width={60} rows={1} />
      </Sheet>
      <Sheet x={29} y={90} width={95} height={35}>
        <Lines x={48} y={105} width={61} rows={1} />
      </Sheet>
      <Sheet x={196} y={90} width={95} height={35}>
        <Lines x={215} y={105} width={60} rows={1} />
      </Sheet>
      <circle cx="160" cy="137" r="7" fill="currentColor" opacity="0.35" />
    </>
  );
}

function Home() {
  return (
    <>
      <path
        d="M48 141V63l111-46 112 46v78Z"
        fill="currentColor"
        fillOpacity="0.025"
        stroke="currentColor"
        strokeOpacity="0.18"
      />
      <path
        d="M75 140v-25h159v25M87 114V91q0-8 8-8h119q8 0 8 8v24M155 84v31"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.45"
        strokeWidth="2"
      />
      <path
        d="M159 18v30m-15 15 15-15 15 15Z"
        stroke="currentColor"
        strokeOpacity="0.6"
        fill="currentColor"
        fillOpacity="0.15"
      />
      <path d="M142 66 117 103h84l-25-37Z" fill="currentColor" opacity="0.07" />
      <Lightbulb x="239" y="24" width="25" height="25" />
    </>
  );
}

function Memory() {
  return (
    <>
      <Sheet x={40} y={26} width={241} height={112}>
        <circle cx="77" cy="61" r="22" fill="currentColor" opacity="0.09" />
        <UserRound x="65" y="49" width="24" height="24" />
        <Lines x={114} y={47} width={143} rows={3} />
        {[59, 127, 195].map((x, i) => (
          <g key={x}>
            <rect
              x={x}
              y="97"
              width="57"
              height="24"
              rx="12"
              fill="currentColor"
              opacity={0.1 + i * 0.07}
            />
            <Lines x={x + 10} y={108} width={39} rows={1} />
          </g>
        ))}
      </Sheet>
      <Heart x="251" y="15" width="24" height="24" className="fill-card" />
    </>
  );
}

function RadioArt() {
  return (
    <>
      <Sheet x={35} y={23} width={251} height={116}>
        <rect x="49" y="38" width="71" height="70" rx="8" fill="currentColor" opacity="0.1" />
        <Radio x="67" y="55" width="35" height="35" />
        <Lines x={136} y={44} width={130} rows={2} />
        <Wave x={139} y={87} width={124} />
        <path
          d="M52 123h192"
          stroke="currentColor"
          strokeOpacity="0.2"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <path
          d="M52 123h67"
          stroke="currentColor"
          strokeOpacity="0.8"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <circle cx="119" cy="123" r="4" fill="currentColor" />
        <Play x="256" y="116" width="15" height="15" />
      </Sheet>
    </>
  );
}

function Briefing() {
  return (
    <>
      <Sheet x={32} y={17} width={255} height={39}>
        <Sun x="46" y="28" width="17" height="17" />
        <Lines x={79} y={28} width={183} rows={2} />
      </Sheet>
      {[CalendarDays, Mail, FileText].map((Icon, i) => (
        <g key={i}>
          <Sheet x={32 + i * 88} y={68} width={79} height={77}>
            <Icon x={45 + i * 88} y="81" width="19" height="19" />
            <Lines x={45 + i * 88} y={114} width={54} rows={2} />
          </Sheet>
        </g>
      ))}
    </>
  );
}

function Automation() {
  return (
    <>
      <path d="M52 29v103" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      {[Mail, CalendarDays, BellRing].map((Icon, i) => (
        <g key={i}>
          <circle
            cx="52"
            cy={35 + i * 44}
            r="16"
            className="fill-card"
            stroke="currentColor"
            strokeOpacity="0.25"
          />
          <Icon x="44" y={27 + i * 44} width="16" height="16" />
          <Sheet x={82} y={19 + i * 44} width={198 - i * 18} height={33}>
            <Lines x={96} y={29 + i * 44} width={148 - i * 18} rows={2} />
          </Sheet>
        </g>
      ))}
    </>
  );
}

function Board() {
  return (
    <>
      {[0, 1, 2].map(col => (
        <g key={col}>
          <rect
            x={28 + col * 89}
            y="20"
            width="79"
            height="120"
            rx="6"
            fill="currentColor"
            opacity="0.04"
          />
          <rect
            x={38 + col * 89}
            y="31"
            width="37"
            height="4"
            rx="2"
            fill="currentColor"
            opacity={0.25 + col * 0.15}
          />
          {[0, 1].slice(0, col === 1 ? 1 : 2).map(row => (
            <g key={row}>
              <Sheet x={35 + col * 89} y={47 + row * 45} width={65} height={36}>
                <Lines x={44 + col * 89} y={57 + row * 45} width={42} rows={2} />
              </Sheet>
            </g>
          ))}
        </g>
      ))}
      <Check x="248" y="73" width="13" height="13" />
      <MousePointer2 x="166" y="111" width="22" height="22" />
    </>
  );
}

function Knowledge() {
  return (
    <>
      <Sheet x={26} y={22} width={112} height={116}>
        <Search x="39" y="33" width="15" height="15" />
        <Lines x={63} y={39} width={56} rows={1} />
        {[60, 83, 106].map(y => (
          <g key={y}>
            <FileText x="39" y={y} width="14" height="14" />
            <Lines x={63} y={y + 3} width={57} rows={1} />
          </g>
        ))}
      </Sheet>
      <path d="M147 79h19" stroke="currentColor" strokeOpacity="0.3" strokeDasharray="3 3" />
      <Sheet x={176} y={37} width={116} height={91}>
        <Lines x={188} y={52} width={86} rows={4} />
        {[191, 216, 241].map(x => (
          <rect
            key={x}
            x={x}
            y="105"
            width="17"
            height="9"
            rx="3"
            fill="currentColor"
            opacity="0.25"
          />
        ))}
      </Sheet>
    </>
  );
}

function Control() {
  return (
    <>
      <Sheet x={54} y={21} width={212} height={119}>
        <ShieldCheck x="72" y="39" width="26" height="26" />
        <Lines x={112} y={42} width={128} rows={3} />
        <rect x="72" y="94" width="78" height="27" rx="7" fill="currentColor" opacity="0.08" />
        <rect x="164" y="94" width="84" height="27" rx="7" fill="currentColor" opacity="0.2" />
        <Check x="197" y="100" width="16" height="16" />
      </Sheet>
      <LockKeyhole x="252" y="14" width="24" height="24" className="fill-card" />
    </>
  );
}

function People() {
  return (
    <>
      <circle cx="64" cy="47" r="21" fill="currentColor" opacity="0.1" />
      <UserRound x="53" y="36" width="22" height="22" />
      <circle cx="253" cy="112" r="21" fill="currentColor" opacity="0.1" />
      <UserRound x="242" y="101" width="22" height="22" />
      <Sheet x={99} y={27} width={176} height={44}>
        <Lines x={113} y={39} width={142} rows={2} />
      </Sheet>
      <Sheet x={38} y={93} width={179} height={43}>
        <CalendarDays x="50" y="105" width="18" height="18" />
        <Lines x={82} y={106} width={114} rows={2} />
      </Sheet>
      <Check x="190" y="116" width="12" height="12" />
    </>
  );
}

function Tools() {
  return (
    <>
      <Sheet x={43} y={15} width={231} height={132}>
        <Lines x={60} y={31} width={130} rows={1} />
        {[0, 1, 2].map(col => (
          <g key={col}>
            <rect
              x={58 + col * 69}
              y="52"
              width="59"
              height="70"
              rx="6"
              fill="currentColor"
              opacity={0.06 + col * 0.06}
            />
            <rect
              x={70 + col * 69}
              y="66"
              width="15"
              height="15"
              rx="4"
              stroke="currentColor"
              strokeOpacity="0.5"
              fill="none"
            />
            <Lines x={70 + col * 69} y={96} width={34} rows={2} />
          </g>
        ))}
        <rect x="61" y="132" width="180" height="3" rx="1.5" fill="currentColor" opacity="0.12" />
      </Sheet>
      <Sparkles x="262" y="3" width="23" height="23" />
    </>
  );
}

function Devices() {
  return (
    <>
      <Sheet x={29} y={20} width={211} height={111}>
        <Lines x={47} y={39} width={113} rows={2} />
        <rect x="83" y="78" width="133" height="33" rx="7" fill="currentColor" opacity="0.1" />
        <Lines x={96} y={89} width={106} rows={2} />
      </Sheet>
      <path d="M112 131v15m-32 0h64" stroke="currentColor" strokeOpacity="0.35" strokeWidth="3" />
      <Sheet x={224} y={55} width={67} height={94}>
        <rect x="243" y="62" width="29" height="3" rx="1.5" fill="currentColor" opacity="0.3" />
        <Lines x={235} y={80} width={42} rows={2} />
        <rect x="236" y="109" width="42" height="23" rx="4" fill="currentColor" opacity="0.15" />
      </Sheet>
    </>
  );
}

function Weather() {
  return (
    <>
      <Sheet x={41} y={23} width={239} height={115}>
        <Sun x="59" y="42" width="38" height="38" />
        <Lines x={114} y={45} width={139} rows={3} />
        {[0, 1, 2, 3, 4].map(i => (
          <g key={i}>
            <circle
              cx={70 + i * 45}
              cy="106"
              r={5 + (i % 2) * 2}
              fill="currentColor"
              opacity={0.2 + i * 0.1}
            />
            <Lines x={61 + i * 45} y={123} width={26} rows={1} />
          </g>
        ))}
      </Sheet>
    </>
  );
}

function Health() {
  return (
    <>
      <Sheet x={35} y={24} width={250} height={112}>
        <Heart x="50" y="39" width="18" height="18" />
        <Lines x={81} y={45} width={116} rows={1} />
        <path d="M51 115h216M51 86h216" stroke="currentColor" strokeOpacity="0.09" />
        <path
          d="m52 101 18-8 20 9 18-26 21 10 21-15 19 16 17-9m19-3 21-15 20 14 20-6"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          fill="none"
        />
        {[52, 108, 150, 226, 266].map((x, i) => (
          <circle key={x} cx={x} cy={[101, 76, 71, 60, 68][i]} r="3" fill="currentColor" />
        ))}
      </Sheet>
    </>
  );
}

const SCENES: Record<FeatureScene, () => ReactNode> = {
  plan: Plan,
  call: Call,
  voice: Voice,
  document: Document,
  browser: Browser,
  calculation: Calculation,
  image: ImageArt,
  diagram: Diagram,
  home: Home,
  memory: Memory,
  radio: RadioArt,
  briefing: Briefing,
  automation: Automation,
  board: Board,
  knowledge: Knowledge,
  control: Control,
  people: People,
  tools: Tools,
  devices: Devices,
  weather: Weather,
  health: Health,
};

/** Static editorial drawing: no fake user data, controls, or runtime status. */
export function FeatureIllustration({ featureKey }: { featureKey: string }) {
  const Scene = SCENES[FEATURE_SCENES[featureKey]] ?? Plan;
  return (
    <div className="rounded-xl border border-primary/10 bg-primary/[0.035] px-3 py-2">
      <svg
        viewBox="0 0 320 160"
        aria-hidden="true"
        focusable="false"
        className="mx-auto h-36 w-full text-primary sm:h-40"
      >
        <Scene />
      </svg>
    </div>
  );
}
