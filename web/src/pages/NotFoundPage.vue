<script setup>
import { useRoute } from "vue-router";

// A Cloudflare-style error page, as on eggtargaryen.com.
const route = useRoute();
const time = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";
const columns = [
  { icon: "browser", status: "error", name: "404", title: "Website", state: "Not Found" },
  { icon: "cloud", status: "ok", name: "Somewhere", title: "Cloud", state: "Working" },
  { icon: "server", status: "ok", name: "Server", title: "Host", state: "Working" },
];
</script>

<template>
  <div class="cf-page">
    <header class="cf-header">
      <h1>Not Found <span class="code-label">Error code 404</span></h1>
      <div class="cf-time">{{ time }}</div>
    </header>
    <div class="cf-band">
      <div class="cf-columns">
        <div v-for="column in columns" :key="column.title" class="cf-column" :class="{ source: column.status === 'error' }">
          <div class="cf-icons">
            <span class="cf-icon" :class="`cf-icon-${column.icon}`" />
            <span class="cf-badge" :class="`cf-icon-${column.status}`" />
          </div>
          <span class="cf-name">{{ column.name }}</span>
          <h3>{{ column.title }}</h3>
          <span class="cf-state" :class="column.status">{{ column.state }}</span>
        </div>
      </div>
    </div>
    <div class="cf-explain">
      <div>
        <h2>What happened?</h2>
        <p>页面 <code>{{ route.path }}</code> 不存在，链接可能已经过期或输入有误。</p>
      </div>
      <div>
        <h2>What can I do?</h2>
        <p><RouterLink to="/">回到首页</RouterLink>，从那里进入各个信息站。</p>
      </div>
    </div>
    <p class="cf-footer">
      <span>Ray ID: <strong>114514</strong></span>
      <span class="separator">&bull;</span>
      <span>Performance &amp; security by <RouterLink to="/">MHWS 数据站</RouterLink></span>
    </p>
  </div>
</template>

<style scoped>
.cf-page {
  max-width: 960px;
  margin: auto;
  color: var(--on-surface);
}
.cf-header {
  padding-top: 16px;
  margin-bottom: 32px;
}
.cf-header h1 {
  font-size: 60px;
  font-weight: 300;
  line-height: 1.25;
}
.code-label {
  display: inline-block;
  vertical-align: middle;
  padding: 4px 10px;
  border-radius: 20px;
  background: var(--surface-high);
  color: var(--on-surface);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.5;
  white-space: nowrap;
}
.cf-time {
  margin-top: 12px;
  color: var(--on-surface-variant);
}
.cf-band {
  margin: 0 -32px 32px;
  background-image: linear-gradient(
    to bottom,
    var(--surface-high) 0%,
    var(--surface) 3%,
    var(--surface) 97%,
    var(--surface-high) 100%
  );
}
.cf-columns {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  max-width: 960px;
  margin: auto;
}
.cf-column {
  position: relative;
  padding: 60px 0;
  text-align: center;
  overflow: hidden;
}
.cf-column.source::after {
  content: "";
  position: absolute;
  bottom: -28px;
  left: 50%;
  width: 40px;
  height: 40px;
  margin-left: -20px;
  background: var(--background);
  transform: rotate(45deg);
  box-shadow: 0 0 4px 4px var(--surface-high);
}
.cf-icons {
  position: relative;
  margin-bottom: 40px;
}
.cf-icon {
  display: block;
  height: 80px;
  background: center / contain no-repeat;
}
.cf-badge {
  position: absolute;
  left: 50%;
  bottom: -16px;
  width: 48px;
  height: 48px;
  margin-left: -24px;
  background: center / contain no-repeat;
}
.cf-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cf-column h3 {
  margin-top: 12px;
  color: var(--on-surface-variant);
  font-size: 24px;
  font-weight: 300;
  line-height: 1.3;
}
.cf-state {
  font-size: 24px;
  line-height: 1.3;
}
.cf-state.error {
  color: #bd2426;
}
.cf-state.ok {
  color: #9bca3e;
}
.cf-explain {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-bottom: 32px;
  line-height: 1.625;
}
.cf-explain h2 {
  margin-bottom: 16px;
  font-size: 30px;
  font-weight: 400;
  line-height: 1.3;
}
.cf-explain code {
  overflow-wrap: anywhere;
}
.cf-page a {
  color: #2f7bbf;
  transition: color 0.15s cubic-bezier(0, 0, 0.2, 1);
}
.dark .cf-page a {
  color: var(--primary);
}
.cf-page a:hover {
  color: #f68b1f;
}
.cf-footer {
  padding: 40px 0;
  border-top: 1px solid var(--outline-variant);
  text-align: center;
  font-size: 13px;
}
.cf-footer strong {
  font-weight: 600;
}
.separator {
  margin: 0 8px;
}
@media (max-width: 720px) {
  .cf-header h1 {
    font-size: 36px;
  }
  .cf-band {
    margin: 0 -20px 32px;
    padding: 0 20px;
  }
  .cf-columns {
    grid-template-columns: 1fr;
  }
  .cf-column {
    padding: 32px 0;
    text-align: left;
    border-bottom: 1px solid var(--outline-variant);
  }
  .cf-column:last-child {
    border-bottom: none;
  }
  .cf-column.source::after,
  .cf-icon {
    display: none;
  }
  .cf-icons {
    position: absolute;
    top: 32px;
    right: 0;
    margin: 0;
  }
  .cf-badge {
    position: static;
    display: block;
    margin: 0;
  }
  .cf-column h3 {
    display: inline-block;
    margin: 0 8px 0 0;
  }
  .cf-explain {
    grid-template-columns: 1fr;
  }
  .cf-footer {
    text-align: left;
  }
  .cf-footer span {
    display: block;
    margin-bottom: 4px;
  }
  .separator {
    display: none !important;
  }
}
.cf-icon-browser {
  background-image: url(data:image/svg+xml;utf8,%3Csvg%20id%3D%22a%22%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%20100%2080.7362%22%3E%3Cpath%20d%3D%22M89.8358.1636H10.1642C4.6398.1636.1614%2C4.6421.1614%2C10.1664v60.4033c0%2C5.5244%2C4.4784%2C10.0028%2C10.0028%2C10.0028h79.6716c5.5244%2C0%2C10.0027-4.4784%2C10.0027-10.0028V10.1664c0-5.5244-4.4784-10.0028-10.0027-10.0028ZM22.8323%2C9.6103c1.9618%2C0%2C3.5522%2C1.5903%2C3.5522%2C3.5521s-1.5904%2C3.5522-3.5522%2C3.5522-3.5521-1.5904-3.5521-3.5522%2C1.5903-3.5521%2C3.5521-3.5521ZM12.8936%2C9.6103c1.9618%2C0%2C3.5522%2C1.5903%2C3.5522%2C3.5521s-1.5904%2C3.5522-3.5522%2C3.5522-3.5521-1.5904-3.5521-3.5522%2C1.5903-3.5521%2C3.5521-3.5521ZM89.8293%2C70.137H9.7312V24.1983h80.0981v45.9387ZM89.8293%2C16.1619H29.8524v-5.999h59.977v5.999Z%22%20style%3D%22fill%3A%20%23999%3B%22/%3E%3C/svg%3E);
}
.cf-icon-cloud {
  background-image: url(data:image/svg+xml;utf8,%3Csvg%20id%3D%22a%22%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%20152%2078.9141%22%3E%3Cpath%20d%3D%22M132.2996%2C77.9927v-.0261c10.5477-.2357%2C19.0305-8.8754%2C19.0305-19.52%2C0-10.7928-8.7161-19.5422-19.4678-19.5422-2.9027%2C0-5.6471.6553-8.1216%2C1.7987C123.3261%2C18.6624%2C105.3419.9198%2C83.202.9198c-17.8255%2C0-32.9539%2C11.5047-38.3939%2C27.4899-3.0292-2.2755-6.7818-3.6403-10.8622-3.6403-10.0098%2C0-18.1243%2C8.1145-18.1243%2C18.1243%2C0%2C1.7331.258%2C3.4033.7122%2C4.9905-.2899-.0168-.5769-.0442-.871-.0442-8.2805%2C0-14.993%2C6.7503-14.993%2C15.0772%2C0%2C8.2795%2C6.6381%2C14.994%2C14.8536%2C15.0701v.0054h.1069c.0109%2C0%2C.0215.0016.0325.0016s.0215-.0016.0325-.0016%22%20style%3D%22fill%3A%20%23999%3B%22/%3E%3C/svg%3E);
}
.cf-icon-server {
  background-image: url(data:image/svg+xml;utf8,%3Csvg%20id%3D%22a%22%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%2095%2075%22%3E%3Cpath%20d%3D%22M94.0103%2C45.0775l-12.9885-38.4986c-1.2828-3.8024-4.8488-6.3624-8.8618-6.3619l-49.91.0065c-3.9995.0005-7.556%2C2.5446-8.8483%2C6.3295L1.0128%2C42.8363c-.3315.971-.501%2C1.9899-.5016%2C3.0159l-.0121%2C19.5737c-.0032%2C5.1667%2C4.1844%2C9.3569%2C9.3513%2C9.3569h75.2994c5.1646%2C0%2C9.3512-4.1866%2C9.3512-9.3512v-17.3649c0-1.0165-.1657-2.0262-.4907-2.9893ZM86.7988%2C65.3097c0%2C1.2909-1.0465%2C2.3374-2.3374%2C2.3374H9.9767c-1.2909%2C0-2.3374-1.0465-2.3374-2.3374v-18.1288c0-1.2909%2C1.0465-2.3374%2C2.3374-2.3374h74.4847c1.2909%2C0%2C2.3374%2C1.0465%2C2.3374%2C2.3374v18.1288Z%22%20style%3D%22fill%3A%20%23999%3B%22/%3E%3Ccircle%20cx%3D%2274.6349%22%20cy%3D%2256.1889%22%20r%3D%224.7318%22%20style%3D%22fill%3A%20%23999%3B%22/%3E%3Ccircle%20cx%3D%2259.1472%22%20cy%3D%2256.1889%22%20r%3D%224.7318%22%20style%3D%22fill%3A%20%23999%3B%22/%3E%3C/svg%3E);
}
.cf-icon-ok {
  background-image: url(data:image/svg+xml;utf8,%3Csvg%20id%3D%22a%22%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%2048%2048%22%3E%3Ccircle%20cx%3D%2224%22%20cy%3D%2224%22%20r%3D%2223.4815%22%20style%3D%22fill%3A%20%239bca3e%3B%22/%3E%3Cpolyline%20points%3D%2217.453%2024.9841%2021.7183%2030.4504%2030.2076%2016.8537%22%20style%3D%22fill%3A%20none%3B%20stroke%3A%20%23fff%3B%20stroke-linecap%3A%20round%3B%20stroke-linejoin%3A%20round%3B%20stroke-width%3A%204px%3B%22/%3E%3C/svg%3E);
}
.cf-icon-error {
  background-image: url(data:image/svg+xml;utf8,%3Csvg%20id%3D%22a%22%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%2047.9145%2047.9641%22%3E%3Ccircle%20cx%3D%2223.9572%22%20cy%3D%2223.982%22%20r%3D%2223.4815%22%20style%3D%22fill%3A%20%23bd2426%3B%22/%3E%3Cline%20x1%3D%2219.0487%22%20y1%3D%2219.0768%22%20x2%3D%2227.8154%22%20y2%3D%2228.8853%22%20style%3D%22fill%3A%20none%3B%20stroke%3A%20%23fff%3B%20stroke-linecap%3A%20round%3B%20stroke-linejoin%3A%20round%3B%20stroke-width%3A%203px%3B%22/%3E%3Cline%20x1%3D%2227.8154%22%20y1%3D%2219.0768%22%20x2%3D%2219.0487%22%20y2%3D%2228.8853%22%20style%3D%22fill%3A%20none%3B%20stroke%3A%20%23fff%3B%20stroke-linecap%3A%20round%3B%20stroke-linejoin%3A%20round%3B%20stroke-width%3A%203px%3B%22/%3E%3C/svg%3E);
}
</style>
