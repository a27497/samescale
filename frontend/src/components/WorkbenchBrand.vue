<template>
  <span class="workbench-brand" translate="no">
    <img class="workbench-brand__outlined" src="/brand/samescale-lockup-cobalt.svg" width="678" height="100" alt="" />
    <img class="workbench-brand__symbol" src="/brand/samescale-symbol-24px-cobalt.svg" width="24" height="24" alt="" />
    <span class="workbench-brand__name">SameScale</span>
  </span>
</template>

<style scoped>
/* Retain the official outlined wordmark, using its dedicated pixel cut at 24px. */
.workbench-brand { position: relative; display: block; width: calc(24px * 6.7799); height: 24px; }
.workbench-brand__outlined { display: block; width: 100%; height: 100%; max-width: none; clip-path: inset(0 0 0 24px); }
.workbench-brand__symbol { position: absolute; inset: 0 auto auto 0; display: block; width: 24px; height: 24px; }
.workbench-brand__name { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
</style>
