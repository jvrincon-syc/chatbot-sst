export type LlamaStop = "parse" | "classify" | "extract";

export type LlamaRoute =
  | "parse"
  | "parse,classify,extract"
  | "classify,parse,extract"
  | "parse,classify"
  | "classify,parse"
  | "parse,extract";

export type LlamaRouteOption = {
  value: LlamaRoute;
  label: string;
  summary: string;
  stops: LlamaStop[];
};

export type LlamaServiceSelection = {
  classifyEnabled: boolean;
  extractEnabled: boolean;
};

export type LlamaStatusRoute = {
  classifyEnabled?: boolean;
  extractEnabled?: boolean;
  callOrder?: string[];
};

export const DEFAULT_LLAMA_ROUTE: LlamaRoute = "classify,parse,extract";

export const LLAMA_ROUTE_OPTIONS: LlamaRouteOption[] = [
  {
    value: "parse",
    label: "Solo Parse",
    summary: "Parse",
    stops: ["parse"],
  },
  {
    value: "parse,classify,extract",
    label: "Parse primero",
    summary: "Parse > Classify > Extract",
    stops: ["parse", "classify", "extract"],
  },
  {
    value: "classify,parse,extract",
    label: "Classify primero",
    summary: "Classify > Parse > Extract",
    stops: ["classify", "parse", "extract"],
  },
  {
    value: "parse,classify",
    label: "Parse, luego Classify",
    summary: "Parse > Classify",
    stops: ["parse", "classify"],
  },
  {
    value: "classify,parse",
    label: "Classify, luego Parse",
    summary: "Classify > Parse",
    stops: ["classify", "parse"],
  },
  {
    value: "parse,extract",
    label: "Parse, luego Extract",
    summary: "Parse > Extract",
    stops: ["parse", "extract"],
  },
];

export function isLlamaRoute(value: string): value is LlamaRoute {
  return LLAMA_ROUTE_OPTIONS.some((option) => option.value === value);
}

export function llamaCloudConfigFromRoute(route: LlamaRoute) {
  const stops = stopsForRoute(route);
  return {
    classifyEnabled: stops.includes("classify"),
    extractEnabled: stops.includes("extract"),
    callOrder: route,
  };
}

export function routeFromStatus(status: LlamaStatusRoute): LlamaRoute {
  const configuredStops = status.callOrder?.length
    ? status.callOrder
    : DEFAULT_LLAMA_ROUTE.split(",");
  const activeStops = configuredStops.filter((stop) => {
    if (stop === "classify" && status.classifyEnabled === false) return false;
    if (stop === "extract" && status.extractEnabled === false) return false;
    return true;
  });
  const route = activeStops.join(",");
  return isLlamaRoute(route) ? route : DEFAULT_LLAMA_ROUTE;
}

export function matchingRoutesForServices(
  services: LlamaServiceSelection,
): LlamaRouteOption[] {
  return LLAMA_ROUTE_OPTIONS.filter((option) => {
    const stops = option.stops;
    return (
      stops.includes("classify") === services.classifyEnabled &&
      stops.includes("extract") === services.extractEnabled
    );
  });
}

export function routeForServiceSelection(
  currentRoute: LlamaRoute,
  services: LlamaServiceSelection,
): LlamaRoute {
  const matchingRoutes = matchingRoutesForServices(services);
  return (
    matchingRoutes.find((option) => option.value === currentRoute)?.value ??
    matchingRoutes[0]?.value ??
    "parse"
  );
}

export function stopsForRoute(route: LlamaRoute): LlamaStop[] {
  const option = LLAMA_ROUTE_OPTIONS.find((candidate) => candidate.value === route);
  return option?.stops ?? ["parse"];
}
